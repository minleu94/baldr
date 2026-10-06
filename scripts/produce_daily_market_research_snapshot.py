"""隔離output的有界日特徵研究快照入口；不部署排程或寫正式資料庫。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from zoneinfo import ZoneInfo

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app_module.daily_market_snapshot_producer import DailyMarketSnapshotInput, DailyMarketSnapshotProducer
from app_module.daily_market_research_universe import load_research_universe_spec
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
    parser.add_argument("--cohort-id")
    parser.add_argument("--decision-cutoff", required=True, help="含時區ISO時刻；轉Asia/Taipei，不能晚於現在。")
    scope_group = parser.add_mutually_exclusive_group(required=True)
    scope_group.add_argument("--symbols", nargs="+", help="1-16 explicit research symbols")
    scope_group.add_argument("--universe-config", help="Strict research-universe JSON; uses its included members")
    scope_group.add_argument("--parent-universe-config", help="具名多批母體 JSON；每批仍≤16股，總批數≤16。")
    parser.add_argument("--read-parent-identity", help="搭配 parent-universe-config/capture-root，唯讀重讀指定 parent；不開 DB/producer。")
    parser.add_argument("--read-stock", help="可選明示cohort內一股，發布後經個股read_report核驗讀回；不觸發live projection。")
    parser.add_argument("--capture-root", help="可選 output/qa 或 Temp 子目錄，明示保存完整單批 MA 控制組。")
    parser.add_argument("--capture-as-of", help="與 capture-root 配對；首次可用 observed-now，之後沿用回傳固定含時區 as_of 才能去重。")
    args = parser.parse_args(argv)
    try:
        cutoff = datetime.fromisoformat(args.decision_cutoff)
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise ValueError("decision_cutoff 必須含時區")
        cutoff = cutoff.astimezone(ZoneInfo("Asia/Taipei"))
        root = _isolated_output(args.output_root)
        if bool(args.capture_root) != bool(args.capture_as_of):
            raise ValueError("capture-root 與 capture-as-of 必須配對")
        capture_writer = None
        capture_as_of = None
        if args.capture_root:
            from app_module.rule_research_sample_capture import BoundedRuleResearchCaptureWriter
            capture_writer = BoundedRuleResearchCaptureWriter(args.capture_root)
            if args.capture_as_of != "observed-now":
                capture_as_of = datetime.fromisoformat(args.capture_as_of)
                if capture_as_of.tzinfo is None or capture_as_of.utcoffset() is None:
                    raise ValueError("capture-as-of 必須含時區或明示 observed-now")
            source_root = root.resolve()
            if capture_writer.output_root.is_relative_to(source_root) or source_root.is_relative_to(capture_writer.output_root):
                raise ValueError("source_output_overlap")
        if args.read_parent_identity and not args.parent_universe_config:
            raise ValueError("read-parent-identity 必須搭配 parent-universe-config")
        if args.parent_universe_config:
            if not args.capture_root or args.read_stock is not None or args.cohort_id is not None:
                raise ValueError("parent 母體需明示 capture-root/capture-as-of；不接受單股read-stock或覆寫cohort-id")
            from app_module.rule_research_parent_capture import produce_parent_rule_samples
            from app_module.rule_research_sample_readiness import read_saved_parent_rule_sample_readiness
            if args.read_parent_identity:
                ready = read_saved_parent_rule_sample_readiness(root, args.capture_root,
                    universe_path=args.parent_universe_config, identity_sha256=args.read_parent_identity)
                if ready["decision_cutoff"] != cutoff.isoformat():
                    raise ValueError("parent_decision_cutoff_mismatch")
                if capture_as_of is not None and ready["as_of"] != capture_as_of.astimezone(timezone.utc).isoformat():
                    raise ValueError("parent_as_of_mismatch")
                print(json.dumps({"status": "readonly", "sample_readiness": ready}, ensure_ascii=False, sort_keys=True))
                return 0
            parent_result = produce_parent_rule_samples(db_path=args.db_path, snapshot_root=root,
                capture_root=args.capture_root, universe_path=args.parent_universe_config,
                decision_cutoff=cutoff, as_of=capture_as_of)
            print(json.dumps(parent_result, ensure_ascii=False, sort_keys=True))
            return 0 if parent_result["status"] == "complete" else 2
        universe_spec = (
            load_research_universe_spec(args.universe_config)
            if args.universe_config is not None
            else None
        )
        symbols = (
            universe_spec.included_stock_codes
            if universe_spec is not None
            else tuple(args.symbols or ())
        )
        cohort_id = (
            universe_spec.universe_id
            if universe_spec is not None and args.cohort_id is None
            else args.cohort_id
        )
        if not cohort_id:
            raise ValueError("--cohort-id is required without --universe-config")
        if universe_spec is not None and cohort_id != universe_spec.universe_id:
            raise ValueError("--cohort-id must match universe_id from --universe-config")
        if not 1 <= len(symbols) <= 16 or len(set(symbols)) != len(symbols):
            raise ValueError("單批母體必須是 1–16 檔不同股票；較大母體請使用 --parent-universe-config；拒絕截斷或拆批冒充完整。")
        if args.read_stock is not None and args.read_stock not in symbols:
            raise ValueError("read_stock 必須屬於明示symbols")
        with SQLiteDailyMarketSnapshotSource(args.db_path, cutoff.date()) as source:
            def load_inputs(code: str, day):
                if day != cutoff.date():
                    raise ValueError("source_decision_date_mismatch")
                points, technical, scope_identity, refs = source.load(code)
                return DailyMarketSnapshotInput(code, scope_identity, points, technical, refs)

            def validate_sources_stable() -> None:
                source.validate_source_stable()
                if universe_spec is not None:
                    universe_spec.assert_source_stable()

            result = DailyMarketSnapshotProducer(root).produce(
                cohort_id=cohort_id, decision_cutoff=cutoff,
                stock_codes=symbols, source_loader=load_inputs,
                before_publish=validate_sources_stable,
                research_universe=universe_spec,
            )
        payload = result.to_dict()
        if result.status not in {"published_complete", "published_partial", "unchanged"}:
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            return 2
        if capture_writer is not None:
            from app_module.daily_market_snapshot_repository import DailyMarketSnapshotRepository
            from app_module.rule_research_sample_readiness import read_saved_rule_sample_readiness
            repository = DailyMarketSnapshotRepository(root)
            if capture_as_of is None:
                capture_as_of = datetime.now(timezone.utc)
            try:
                captured = capture_writer.capture_pinned(repository, manifest_sha256=result.manifest_sha256,
                    cohort_id=cohort_id, decision_date=cutoff.date(), as_of=capture_as_of)
                identity = captured["receipt"]["capture_identity_sha256"]
                payload["sample_capture"] = captured
                payload["sample_readiness"] = read_saved_rule_sample_readiness(
                    capture_writer, repository, identity_sha256=identity,
                    manifest_sha256=result.manifest_sha256, cohort_id=cohort_id,
                    decision_date=cutoff.date(), as_of=capture_as_of)
            except Exception as exc:
                # 上游快照可能已發布；保留其收據，不把 capture 失敗當全部未寫入。
                payload["sample_capture_status"] = "rejected"
                payload["sample_capture_error"] = {"type": type(exc).__name__, "code": getattr(exc, "code", ""), "message": str(exc)}
                print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
                return 2
        if args.read_stock is not None:
            from app_module.stock_research_report_service import StockResearchReportReadService
            report = StockResearchReportReadService(
                SimpleNamespace(db_file=Path(args.db_path), output_root=None),
                daily_market_snapshot_root=root, daily_market_snapshot_cohort_id=cohort_id,
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
