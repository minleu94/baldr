"""明選原件的月營收研究歸檔、歷史分批擷取與版本查詢入口。"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import stat
from pathlib import Path
import sys
from typing import cast
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_module.mops_monthly_revenue_history import (
    MAX_MOPS_MONTHLY_REVENUE_HISTORY_PLAN_CHUNK_RECEIPT_BYTES,
    capture_mops_monthly_revenue_history_plan_chunk,
    plan_mops_monthly_revenue_history_capture,
    read_mops_monthly_revenue_history_capture,
    write_mops_monthly_revenue_history_capture_create_only,
)
from data_module.monthly_revenue_revision_archive import (
    append_monthly_revenue_batch, raw_batch_from_openapi,
    read_monthly_revenue_revision_archive, select_monthly_revenue_observation_as_of,
)
from data_module.opendata_monthly_revenue import (
    MAX_OPENAPI_MONTHLY_REVENUE_BYTES, OPENAPI_MONTHLY_REVENUE_ENDPOINTS,
    OpenApiMarket, OpenApiMonthlyRevenueBatch, OpenApiMonthlyRevenueCapture,
    prepare_openapi_monthly_revenue_batch,
)
from data_module.monthly_revenue_qualification_binding import PinnedMonthlyRevenueQualificationResolver
from app_module.monthly_revenue_research_service import MonthlyRevenueResearchFact, MonthlyRevenueResearchService


def _output_path(value: str) -> Path:
    """此研究入口只能寫 repo output；不解析或建立正式資料根。"""
    target = Path(value).absolute().resolve()
    parent = (ROOT / "output").resolve(strict=True)
    if not target.is_relative_to(parent) or target == parent:
        raise ValueError("destination_must_be_under_repository_output")
    return target


def _json_bytes(value: object) -> bytes:
    def encode(item: object) -> str:
        if isinstance(item, (datetime, Decimal)):
            if isinstance(item, Decimal):
                return str(item)
            return item.isoformat()
        raise TypeError(type(item).__name__)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                      allow_nan=False, default=encode).encode("utf-8")


def _read_bounded(path: Path, limit: int) -> bytes:
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or
            getattr(before, "st_file_attributes", 0) & 0x400 or before.st_size > limit):
        raise ValueError("input_file_missing_or_exceeds_limit")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
                before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
            raise ValueError("input_file_changed_during_open")
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns,
                                 item.st_nlink, item.st_mode)
        if identity(after) != identity(opened) or identity(path.lstat()) != identity(before):
            raise ValueError("input_file_changed_during_read")
    if len(raw) > limit:
        raise ValueError("input_file_exceeds_limit")
    return raw


def _write_report(path: Path, value: object) -> None:
    payload = _json_bytes(value)
    if len(payload) > MAX_MOPS_MONTHLY_REVENUE_HISTORY_PLAN_CHUNK_RECEIPT_BYTES:
        raise ValueError("report_exceeds_bounded_chunk_receipt_limit")
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def read_openapi_capture_batches(capture_directory: str, receipt_sha256: str) -> tuple[OpenApiMonthlyRevenueBatch, ...]:
    """重驗明選雙市場原件；不下載、轉換金額或簽發來源資格。"""
    source = Path(capture_directory).absolute()
    receipt_raw = _read_bounded(source / "receipt.json", 128 * 1024)
    if hashlib.sha256(receipt_raw).hexdigest() != receipt_sha256:
        raise ValueError("capture_receipt_external_sha256_mismatch")
    receipt = json.loads(receipt_raw)
    sources = receipt["sources"]
    if len(sources) != 2 or {item["market"] for item in sources} != {"twse", "tpex"}:
        raise ValueError("capture_receipt_market_pair_invalid")
    batches = []
    for item in sources:
        market = cast(OpenApiMarket, item["market"])
        raw = _read_bounded(source / "raw" / (market + ".json"), MAX_OPENAPI_MONTHLY_REVENUE_BYTES)
        if hashlib.sha256(raw).hexdigest() != item["raw_response_sha256"]:
            raise ValueError("capture_raw_sha256_mismatch:" + market)
        if item["requested_url"] != OPENAPI_MONTHLY_REVENUE_ENDPOINTS[market]:
            raise ValueError("capture_source_identity_mismatch")
        completed = datetime.fromisoformat(item["body_completed_at"])
        capture = OpenApiMonthlyRevenueCapture(
            market=market, requested_url=item["requested_url"], response_url=item["response_url"],
            response_status=item["response_status"],
            content_type_original_text=item["content_type_original_text"],
            content_encoding_original_text=item["content_encoding_original_text"],
            content_length_original_text=item["content_length_original_text"],
            response_body_complete=item["response_body_complete"], eof_observed=item["eof_observed"],
            received_body_bytes=item["received_body_bytes"],
            body_observation_ended_at=datetime.fromisoformat(item["body_observation_ended_at"]),
            body_completed_at=completed, raw_response_bytes=raw,
        )
        batch = prepare_openapi_monthly_revenue_batch(
            capture=capture, successful_batch_completed_at=completed)
        batches.append(batch)
    if len({row.period for batch in batches for row in batch.rows}) != 1:
        raise ValueError("capture_market_period_pair_mismatch")
    return tuple(batches)


def _import_openapi(args: argparse.Namespace) -> dict[str, object]:
    batches = read_openapi_capture_batches(args.capture_directory, args.receipt_sha256)
    destination = _output_path(args.archive_root)
    parent_hash = args.parent_sha256
    counts: dict[str, int] = {}
    missing: dict[str, dict[str, int]] = {}
    for batch in batches:
        market = batch.capture.market
        result = append_monthly_revenue_batch(destination, raw_batch_from_openapi(batch),
                                              archive_sha256=parent_hash,
                                              expected_archive_sha256=parent_hash)
        parent_hash = result.archive_sha256
        counts[market] = len(batch.rows)
        missing[market] = {}
        for row in batch.rows:
            for field, value in row.percentage_values:
                if value is None:
                    missing[market][field] = missing[market].get(field, 0) + 1
    if parent_hash is None:
        raise ValueError("capture_receipt_market_pair_empty")
    archive = read_monthly_revenue_revision_archive(destination, parent_hash,
                                                   expected_archive_sha256=parent_hash)
    return {"status": "archived_raw_candidates", "archive_root": str(destination),
            "archive_sha256": archive.archive_sha256, "counts": counts,
            "percentage_unknown_counts": missing, "amount_unit": "unknown_no_twd_conversion",
            "formal_pit_eligible": False, "source_qualification_created": False,
            "attribution": "金融監督管理委員會證券期貨局／TWSE／TPEx，每月營業收入彙總表；https://data.gov.tw/license；衍生整理：Baldr"}


def _research_current(args: argparse.Namespace) -> dict[str, object]:
    """同一次操作重新讀取資格包；只輸出通過個別用途門的研究結果。"""
    cutoff = datetime.fromisoformat(args.cutoff_at) if args.cutoff_at else datetime.now(timezone.utc)
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("research_cutoff_must_be_timezone_aware")
    threshold = Decimal(args.minimum) if args.minimum is not None else None
    if threshold is not None and not threshold.is_finite():
        raise ValueError("research_minimum_must_be_finite")
    bindings = args.binding
    if len(bindings) != 2 or {item[0] for item in bindings} != {"twse", "tpex"}:
        raise ValueError("research_requires_exact_market_binding_pair")
    resolvers = {market: PinnedMonthlyRevenueQualificationResolver(Path(path), digest)
                 for market, path, digest in bindings}
    batches = read_openapi_capture_batches(args.capture_directory, args.receipt_sha256)
    facts: list[MonthlyRevenueResearchFact] = []
    services = {}
    snapshots = []
    for batch in batches:
        market = batch.capture.market
        resolver = resolvers[market]
        evidence = resolver.evidence_for_batch(batch)
        service = MonthlyRevenueResearchService(qualification_verifier=resolver.verify)
        services[market] = service
        items = service.current_openapi_facts(batch, metric=args.metric, evidence=evidence,
                                             cutoff_at=cutoff)
        facts.extend(items)
        snapshots.append(service.sector_theme_shadow_snapshot(
            items, decision_date=cutoff.astimezone(ZoneInfo("Asia/Taipei")).date(),
            cutoff_at=cutoff, universe_id="monthly-revenue-explicit-capture:" + market).to_dict())
    rows = [{"market": item.market, "stock_code": item.stock_code, "period": item.period,
             "metric": item.metric, "value": item.value, "unit": item.unit,
             "allowed": item.allowed, "reasons": item.decision.reasons,
             "missing_reason": item.missing_reason, "source_id": item.source_id,
             "source_version": item.source_version, "batch_sha256": item.batch_sha256,
             "available_at": item.available_at, "formal_pit_eligible": item.formal_pit_eligible}
            for item in facts]
    result: dict[str, object] = {
        "status": "research_projected", "cutoff_at": cutoff, "metric": args.metric,
        "rows": rows, "market_shadow_snapshots": snapshots,
        "qualified_count": sum(item.allowed for item in facts),
        "unknown_count": sum(item.value is None for item in facts),
        "amount_unit": "unknown_no_twd_conversion", "formal_pit_eligible": False,
        "formal_scoring_engine_enabled": False,
        "attribution": "金融監督管理委員會證券期貨局／TWSE／TPEx，每月營業收入彙總表；https://data.gov.tw/license；衍生整理：Baldr",
    }
    if threshold is not None:
        screened = [services[batch.capture.market].screen_minimum(
            (item for item in facts if item.market == batch.capture.market),
            minimum=threshold, cutoff_at=cutoff) for batch in batches]
        result["screen"] = {"minimum": threshold,
                            "matched_keys": [[item.market, item.stock_code] for group in screened for item in group.matched],
                            "unknown_keys": [[item.market, item.stock_code] for group in screened for item in group.unknown],
                            "rejected_keys": [[item.market, item.stock_code] for group in screened for item in group.rejected]}
    return result


def _import_history(args: argparse.Namespace) -> dict[str, object]:
    capture = read_mops_monthly_revenue_history_capture(
        Path(args.capture_file).absolute().resolve(strict=True), expected_sha256=args.capture_sha256)
    destination = _output_path(args.archive_root)
    appended = append_monthly_revenue_batch(
        destination, capture.to_monthly_revenue_raw_batch_evidence(),
        archive_sha256=args.parent_sha256, expected_archive_sha256=args.parent_sha256)
    reopened = read_monthly_revenue_revision_archive(
        destination, appended.archive_sha256, expected_archive_sha256=appended.archive_sha256)
    return {"status": "archived_retrospective_candidate", "market": capture.market,
            "period": capture.period, "row_count": len(capture.rows),
            "archive_root": str(destination), "archive_sha256": reopened.archive_sha256,
            "source_id": capture.source_id, "raw_source_sha256": capture.raw_response_sha256,
            "license_status": "not_accepted_for_use", "amount_unit": "unknown_no_twd_conversion",
            "formal_pit_eligible": False, "source_qualification_created": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    imported = commands.add_parser("import-opendata-capture")
    imported.add_argument("--capture-directory", required=True)
    imported.add_argument("--receipt-sha256", required=True)
    imported.add_argument("--archive-root", required=True)
    imported.add_argument("--parent-sha256")
    history_import = commands.add_parser("import-history-capture")
    history_import.add_argument("--capture-file", required=True)
    history_import.add_argument("--capture-sha256", required=True)
    history_import.add_argument("--archive-root", required=True)
    history_import.add_argument("--parent-sha256")
    research = commands.add_parser("research-current")
    research.add_argument("--capture-directory", required=True)
    research.add_argument("--receipt-sha256", required=True)
    research.add_argument("--binding", action="append", nargs=3, metavar=("MARKET", "PATH", "SHA256"), required=True)
    research.add_argument("--metric", choices=("revenue_yoy_percent", "revenue_mom_percent", "cumulative_revenue_yoy_percent"), default="revenue_yoy_percent")
    research.add_argument("--minimum", help="明選研究篩選下限；無預設條件")
    research.add_argument("--cutoff-at", help="具時區的觀測截止時間；預設本次操作時間")
    for name in ("plan-history", "capture-history-chunk"):
        sub = commands.add_parser(name)
        sub.add_argument("--start-period", required=True)
        sub.add_argument("--end-period", required=True)
        sub.add_argument("--markets", nargs="+", choices=("twse", "tpex"), default=["twse", "tpex"])
        if name == "capture-history-chunk":
            sub.add_argument("--plan-sha256", required=True)
            sub.add_argument("--cursor")
            sub.add_argument("--capture-root", required=True)
            sub.add_argument("--transport-mode", choices=("direct_static_v1", "redirect_chain_v1"),
                             default="direct_static_v1")
    query = commands.add_parser("query")
    query.add_argument("--archive-root", required=True)
    query.add_argument("--archive-sha256", required=True)
    query.add_argument("--market", required=True, choices=("twse", "tpex"))
    query.add_argument("--stock-code", required=True)
    query.add_argument("--period", required=True)
    query.add_argument("--cutoff-at", required=True)
    parser.add_argument("--report", help="另存新的 repo output 收據；不覆寫")
    args = parser.parse_args(argv)
    code = 0
    try:
        if args.command == "import-opendata-capture":
            result = _import_openapi(args)
        elif args.command == "research-current":
            result = _research_current(args)
        elif args.command == "import-history-capture":
            result = _import_history(args)
        elif args.command in {"plan-history", "capture-history-chunk"}:
            plan = plan_mops_monthly_revenue_history_capture(
                start_period=args.start_period, end_period=args.end_period, markets=tuple(args.markets))
            result = plan.to_dict()
            if args.command == "capture-history-chunk":
                if plan.plan_sha256 != args.plan_sha256:
                    raise ValueError("history_plan_external_sha256_mismatch")
                destination = _output_path(args.capture_root)
                if destination.exists():
                    raise ValueError("capture_destination_must_be_new")
                destination.mkdir(parents=True)
                chunk = capture_mops_monthly_revenue_history_plan_chunk(
                    plan, cursor=args.cursor, transport_mode=args.transport_mode)
                result = chunk.to_dict()
                result["data_status"] = "capture_failed" if chunk.batch.failures else "captured_retrospective_candidates"
                result["transport_mode"] = args.transport_mode
                for capture in chunk.batch.captures:
                    write_mops_monthly_revenue_history_capture_create_only(
                        destination / (capture.market + "_" + capture.period + ".json"), capture)
                result["capture_root"] = str(destination)
                code = 2 if chunk.batch.failures else 0
                _write_report(destination / "CHUNK_RECEIPT.json", result)
        else:
            archive = read_monthly_revenue_revision_archive(
                Path(args.archive_root).absolute(), args.archive_sha256,
                expected_archive_sha256=args.archive_sha256)
            selected = select_monthly_revenue_observation_as_of(
                archive, market=args.market, stock_code=args.stock_code,
                period=args.period, cutoff_at=datetime.fromisoformat(args.cutoff_at))
            result = asdict(selected)
        result["writes_formal_data"] = False
        result["owner_authorization"] = "FULL_SCOPE_MONTHLY_REVENUE_OWNER_AUTHORIZATION"
    except (OSError, ValueError, KeyError, TypeError, InvalidOperation) as exc:
        result = {"status": "rejected", "error_type": type(exc).__name__, "error": str(exc),
                  "writes_formal_data": False}
        code = 2
    if args.report:
        report = _output_path(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        _write_report(report, result)
    print(_json_bytes(result).decode("utf-8"))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
