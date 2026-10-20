"""唯讀抓取 MOPS 秒級季報公告，僅輸出至顯式 TEMP／shadow root。"""

from __future__ import annotations

import argparse
import csv
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import sys

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_module.fundamental_statement_availability_sources import (
    STATEMENT_AVAILABILITY_COLUMNS,
)
from data_module.mops_ezsearch_statement_availability import (
    MOPS_MARKETS,
    TAIPEI_TIMEZONE,
    MOPSQueryAttempt,
    MOPSQueryResult,
    MOPSQueryResponseError,
    MOPS_STATEMENT_ITEMS,
    build_statement_availability_artifact,
    query_mops_ezsearch,
)
from data_module.mops_success_response_custody import (
    MOPS_SUCCESS_CUSTODY_DIRECTORY,
    MOPSSuccessResponseCustodyWriter,
    read_mops_success_response_custody,
    write_mops_success_response_readback,
)
from development_module.output_guard import validate_development_output_root


def main(argv: list[str] | None = None) -> int:
    _configure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument(
        "--last-complete-taipei-7-days",
        action="store_true",
        help="啟用固定 weekly research preset：最近完整七個台北曆日、六筆固定查詢、repo 內 create-only run",
    )
    parser.add_argument(
        "--markets",
        default=None,
        help="逗號分隔：sii,otc,rotc,pub",
    )
    parser.add_argument(
        "--items",
        default=None,
        help="逗號分隔：F26,F27,F28,F29",
    )
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--artifact-name")
    parser.add_argument("--mapping-name")
    parser.add_argument("--timeout-seconds", type=int)
    parser.add_argument(
        "--query-retries",
        type=int,
        default=None,
        help="每個 query 的額外重試次數（0–1，最多共 2 次嘗試）；僅 retryable transport／invalid JSON 會重試",
    )
    parser.add_argument(
        "--query-window-days",
        type=int,
        default=None,
        help="每個 market/item query 的日期窗口（1–31 天）；遇到 MOPS 1000 列上限時請縮小",
    )
    parser.add_argument(
        "--capture-success-response-custody",
        action="store_true",
        help="另以 create-only sidecar 保存每筆成功 HTTP response 的完整 encoded bytes",
    )
    args = parser.parse_args(argv)

    weekly_mode = args.last_complete_taipei_7_days
    weekly_overrides = (
        args.start_date,
        args.end_date,
        args.markets,
        args.items,
        args.output_root,
        args.artifact_name,
        args.mapping_name,
        args.timeout_seconds,
        args.query_retries,
        args.query_window_days,
        args.capture_success_response_custody,
    )
    has_weekly_override = any(
        value is not None for value in weekly_overrides[:-1]
    ) or weekly_overrides[-1] is True
    if weekly_mode and has_weekly_override:
        parser.error(
            "--last-complete-taipei-7-days 是固定 preset，不接受日期、查詢範圍、輸出路徑或重試覆寫"
        )
    if not weekly_mode and (args.start_date is None or args.end_date is None):
        parser.error("一般查詢必須同時提供 --start-date 與 --end-date")
    markets: tuple[str, ...]
    items: tuple[str, ...]
    if weekly_mode:
        observed_now = datetime.now(timezone.utc)
        start_date: date
        end_date: date
        start_date, end_date = _last_complete_taipei_7_day_window(observed_now)
        markets = ("sii", "otc")
        items = ("F26", "F27", "F28")
        timeout_seconds = 30
        query_retries = 0
        query_window_days = 7
        artifact_name = "mops-statement-availability.json"
        mapping_name = "fundamental-statement-availability.csv"
        capture_success_response_custody = True
        requested_output_root = ROOT / "output" / "research" / "mops_statement_availability"
    else:
        observed_now = None
        assert args.start_date is not None and args.end_date is not None
        start_date, end_date = args.start_date, args.end_date
        markets = _parse_choices(
            args.markets or ",".join(MOPS_MARKETS), set(MOPS_MARKETS), "markets"
        )
        items = _parse_choices(
            args.items or ",".join(MOPS_STATEMENT_ITEMS), set(MOPS_STATEMENT_ITEMS), "items"
        )
        timeout_seconds = args.timeout_seconds if args.timeout_seconds is not None else 30
        query_retries = args.query_retries if args.query_retries is not None else 0
        query_window_days = args.query_window_days if args.query_window_days is not None else 31
        artifact_name = args.artifact_name or "mops-statement-availability.json"
        mapping_name = args.mapping_name or "fundamental-statement-availability.csv"
        capture_success_response_custody = args.capture_success_response_custody
        if args.output_root is None:
            parser.error("一般查詢必須提供 --output-root")
        requested_output_root = args.output_root
    if end_date < start_date:
        parser.error("--end-date 不得早於 --start-date")
    if (end_date - start_date).days >= 31:
        parser.error("單次查詢最多 31 天，避免碰到 MOPS 1000 筆截斷上限")
    if timeout_seconds <= 0:
        parser.error("--timeout-seconds 必須大於 0")
    if not 0 <= query_retries <= 1:
        parser.error("--query-retries 必須介於 0 與 1 之間（每個 query 最多 2 次嘗試）")
    if not 1 <= query_window_days <= 31:
        parser.error("--query-window-days 必須介於 1 與 31 之間")

    # Resolve protected roots without constructing TWStockConfig: its
    # initialization creates output/data directories, while this collector is
    # an isolated read-only source observer.
    data_root = Path(
        os.environ.get("DATA_ROOT", "F:/Min/Python/Project/FA_Data")
    ).expanduser()
    safe_root = validate_development_output_root(
        requested_output_root,
        data_root=data_root,
        formal_db=data_root / "sqlite" / "twstock.db",
    )
    if weekly_mode:
        try:
            safe_root.relative_to(ROOT.resolve())
        except ValueError:
            parser.error("weekly research output-root 必須位於 repository 內")
        safe_root.mkdir(parents=True, exist_ok=True)
        assert observed_now is not None
        run_id = "run_" + observed_now.strftime("%Y%m%dT%H%M%S%fZ")
        safe_root = safe_root / run_id
        if safe_root.exists() or safe_root.is_symlink():
            parser.error("weekly MOPS run root 已存在；不可覆寫既有 capture")
        safe_root.mkdir(exist_ok=False)
    artifact_path = _safe_output_path(safe_root, artifact_name)
    mapping_path = _safe_output_path(safe_root, mapping_name)
    if artifact_path.exists() or mapping_path.exists():
        parser.error(
            "output artifacts already exist; choose a new run-specific --output-root "
            "to preserve previous receipts"
        )
    raw_failure_root = safe_root / "raw_failed_attempts"
    if raw_failure_root.is_symlink() or (
        raw_failure_root.exists()
        and (
            not raw_failure_root.is_dir()
            or any(raw_failure_root.rglob("*"))
        )
    ):
        parser.error(
            "raw_failed_attempts is not an empty run-specific directory; "
            "choose a new --output-root to preserve previous receipts"
        )
    custody_writer: MOPSSuccessResponseCustodyWriter | None = None
    if capture_success_response_custody:
        capture_root = safe_root / MOPS_SUCCESS_CUSTODY_DIRECTORY
        if capture_root.exists() or capture_root.is_symlink():
            parser.error(
                "raw_success_responses already exists; choose a new --output-root "
                "to preserve previous receipts"
            )
        safe_root.mkdir(parents=True, exist_ok=True)
        custody_writer = MOPSSuccessResponseCustodyWriter(
            run_root=safe_root,
            capture_root=capture_root,
        )

    query_windows = _iter_date_windows(
        start_date,
        end_date,
        window_days=query_window_days,
    )
    if weekly_mode and (
        len(markets) != 2
        or tuple(markets) != ("sii", "otc")
        or tuple(items) != ("F26", "F27", "F28")
        or timeout_seconds != 30
        or query_retries != 0
        or query_window_days != 7
        or len(query_windows) != 1
    ):
        raise RuntimeError("weekly MOPS preset differs from its fixed six-query contract")
    results_list: list[MOPSQueryResult] = []
    with requests.Session() as session:
        for market in markets:
            for item in items:
                for query_start, query_end in query_windows:
                    result = _query_with_retries(
                        session,
                        market=market,
                        announcement_item=item,
                        start_date=query_start,
                        end_date=query_end,
                        timeout_seconds=timeout_seconds,
                        max_retries=query_retries,
                        raw_failure_receipt_root=raw_failure_root,
                        capture_success_entity=custody_writer is not None,
                    )
                    if custody_writer is not None:
                        custody_writer.add_result(result)
                    results_list.append(result)
    results = tuple(results_list)

    captured_at = datetime.now(timezone.utc).isoformat()
    artifact = build_statement_availability_artifact(
        results,
        start_date=start_date,
        end_date=end_date,
        captured_at=captured_at,
    )
    artifact_text = json.dumps(artifact, ensure_ascii=False, indent=2) + "\n"
    mapping_text: str | None = None
    if custody_writer is not None:
        mapping_stream = io.StringIO(newline="")
        mapping_writer = csv.DictWriter(
            mapping_stream,
            fieldnames=STATEMENT_AVAILABILITY_COLUMNS,
        )
        mapping_writer.writeheader()
        mapping_writer.writerows(artifact["availability_projection"])
        mapping_text = mapping_stream.getvalue()
        upper_artifact_bytes = len(artifact_text.encode("utf-8")) + artifact_text.count("\n")
        mapping_bytes = len(mapping_text.encode("utf-8-sig"))
        custody_writer.reserve_for_output(upper_artifact_bytes + mapping_bytes)
    safe_root.mkdir(parents=True, exist_ok=True)
    with artifact_path.open("x", encoding="utf-8") as handle:
        handle.write(artifact_text)
    if custody_writer is not None and mapping_text is not None:
        with mapping_path.open("x", encoding="utf-8-sig", newline="") as handle:
            handle.write(mapping_text)
    else:
        with mapping_path.open("x", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=STATEMENT_AVAILABILITY_COLUMNS)
            writer.writeheader()
            writer.writerows(artifact["availability_projection"])
    custody_receipt: dict[str, object] | None = None
    if custody_writer is not None:
        custody_receipt = custody_writer.finalize(artifact_path=artifact_path)
        write_mops_success_response_readback(
            capture_root=safe_root / MOPS_SUCCESS_CUSTODY_DIRECTORY,
            artifact_path=artifact_path,
        )
        custody_readback = read_mops_success_response_custody(
            capture_root=safe_root / MOPS_SUCCESS_CUSTODY_DIRECTORY,
            artifact_path=artifact_path,
        )
        if custody_readback.get("source_readback_status") != "verified":
            raise RuntimeError("MOPS source readback was not verified")
    else:
        custody_readback = None

    summary = {
        "artifact_path": str(artifact_path),
        "mapping_path": str(mapping_path),
        "event_count": artifact["quality_summary"]["event_count"],
        "projection_count": artifact["quality_summary"]["projection_count"],
        "successful_query_count": artifact["quality_summary"]["successful_query_count"],
        "official_no_data_query_count": artifact["quality_summary"][
            "official_no_data_query_count"
        ],
        "failed_query_count": artifact["quality_summary"]["failed_query_count"],
        "invalid_event_count": artifact["quality_summary"]["invalid_event_count"],
        "status": (
            "ready"
            if artifact["quality_summary"]["failed_query_count"] == 0
            and artifact["quality_summary"]["invalid_event_count"] == 0
            and artifact["quality_summary"]["successful_query_count"] > 0
            else "degraded"
            if artifact["quality_summary"]["successful_query_count"] > 0
            else "unavailable"
        ),
        "formal_oos_allowed": False,
        "formal_credit_authorized": False,
        "production_blend_alpha_bp": 0,
    }
    if custody_receipt is not None:
        summary["successful_response_custody_path"] = str(
            safe_root / MOPS_SUCCESS_CUSTODY_DIRECTORY / "capture_receipt.json"
        )
        summary["successful_response_custody_component_count"] = custody_receipt[
            "component_count"
        ]
        summary["successful_response_source_readback"] = custody_readback[
            "source_readback_status"
        ] if custody_readback is not None else "missing"
    weekly_exit_code = 0
    if weekly_mode:
        query_count = len(query_windows) * len(markets) * len(items)
        successful_count = int(summary["successful_query_count"])
        no_data_count = int(summary["official_no_data_query_count"])
        failed_count = int(summary["failed_query_count"])
        invalid_event_count = int(summary["invalid_event_count"])
        if failed_count or invalid_event_count or successful_count + no_data_count != query_count:
            weekly_research_status = "partial_failure"
            weekly_exit_code = 3
        elif successful_count == 0 and no_data_count == query_count:
            weekly_research_status = "official_no_data"
        elif successful_count > 0:
            weekly_research_status = "captured_research"
        else:
            weekly_research_status = "partial_failure"
            weekly_exit_code = 3
        summary["status"] = weekly_research_status
        summary["weekly_research_status"] = weekly_research_status
        weekly_status = {
            "schema_version": "mops-weekly-research-capture-status.v1",
            "status": weekly_research_status,
            "run_id": safe_root.name,
            "selected_start_date": start_date.isoformat(),
            "selected_end_date": end_date.isoformat(),
            "market_count": len(markets),
            "item_count": len(items),
            "query_count": len(query_windows) * len(markets) * len(items),
            "collection_started_at_utc": (
                custody_receipt.get("collection_started_at_utc")
                if custody_receipt is not None
                else None
            ),
            "artifact_captured_at_utc": (
                custody_receipt.get("artifact_captured_at_utc")
                if custody_receipt is not None
                else None
            ),
            "collection_completed_at_utc": (
                custody_receipt.get("collection_completed_at_utc")
                if custody_receipt is not None
                else None
            ),
            "successful_query_count": summary["successful_query_count"],
            "official_no_data_query_count": summary["official_no_data_query_count"],
            "failed_query_count": summary["failed_query_count"],
            "artifact_path": str(artifact_path),
            "artifact_sha256": (
                custody_readback.get("artifact_sha256")
                if custody_readback is not None
                else None
            ),
            "custody_receipt_path": str(
                safe_root / MOPS_SUCCESS_CUSTODY_DIRECTORY / "capture_receipt.json"
            ),
            "source_readback_status": (
                custody_readback.get("source_readback_status")
                if custody_readback is not None
                else "not_enabled"
            ),
            "research_only": True,
            "formal_oos_allowed": False,
            "formal_credit_authorized": False,
        }
        _write_create_only_json(safe_root / "weekly_research_status.json", weekly_status)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if weekly_mode:
        return weekly_exit_code
    return (
        0
        if artifact["quality_summary"]["successful_query_count"] > 0
        and artifact["quality_summary"]["invalid_event_count"] == 0
        else 3
    )


def _configure_utf8_stdio() -> None:
    """讓 Windows 主控台能輸出繁體中文說明與結構化結果。"""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            # pytest capture streams 或 host-managed stream 可能不可重設編碼。
            continue


def _last_complete_taipei_7_day_window(observed_at: datetime) -> tuple[date, date]:
    """回傳實際觀測時點之前最近完整的七個台北曆日。"""

    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("weekly preset observed_at must be timezone-aware")
    end_date = observed_at.astimezone(TAIPEI_TIMEZONE).date() - timedelta(days=1)
    return end_date - timedelta(days=6), end_date


def _write_create_only_json(path: Path, payload: dict[str, object]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(encoded)


def _safe_query(
    session: requests.Session,
    *,
    market: str,
    announcement_item: str,
    start_date: date,
    end_date: date,
    timeout_seconds: int,
    attempt_number: int = 1,
    capture_success_entity: bool = False,
) -> MOPSQueryResult:
    started_at_utc = datetime.now(timezone.utc).isoformat()
    try:
        return query_mops_ezsearch(
            session,
            market=market,
            announcement_item=announcement_item,
            start_date=start_date,
            end_date=end_date,
            timeout_seconds=timeout_seconds,
            attempt_number=attempt_number,
            capture_success_entity=capture_success_entity,
        )

    except MOPSQueryResponseError as exc:
        attempt = exc.attempt
        material = _error_hash_material(
            market=market,
            announcement_item=announcement_item,
            start_date=start_date,
            end_date=end_date,
            error_code=attempt.error_code,
        )
        return MOPSQueryResult(
            market=market,
            announcement_item=announcement_item,
            rows=(),
            response_sha256=sha256(material.encode("utf-8")).hexdigest(),
            source_status="error",
            error_code=attempt.error_code,
            query_start_date=start_date,
            query_end_date=end_date,
            attempt_count=1,
            attempts=(attempt,),
        )
    except (requests.RequestException, ValueError) as exc:
        error_code = (
            "network_timeout"
            if isinstance(exc, requests.Timeout)
            or "timeout" in type(exc).__name__.lower()
            or "timed out" in str(exc).lower()
            else "network_error"
            if isinstance(exc, requests.RequestException)
            else "invalid_response"
        )
        reason = " ".join(str(exc).split())[:512]
        completed_at_utc = datetime.now(timezone.utc).isoformat()
        response = getattr(exc, "response", None)
        http_status = getattr(response, "status_code", None)
        try:
            http_status = int(http_status) if http_status is not None else None
        except (TypeError, ValueError):
            http_status = None
        retryable = isinstance(
            exc,
            (
                requests.Timeout,
                requests.ConnectionError,
                requests.exceptions.ChunkedEncodingError,
            ),
        )
        if isinstance(exc, requests.HTTPError) and http_status is not None:
            retryable = http_status == 429 or http_status >= 500
        attempt = MOPSQueryAttempt(
            attempt_number=attempt_number,
            started_at_utc=started_at_utc,
            completed_at_utc=completed_at_utc,
            source_status="error",
            error_code=error_code,
            error_type=type(exc).__name__,
            error_reason=reason,
            http_status=http_status,
            http_reason=str(getattr(response, "reason", "") or "")[:160],
            content_type=str(
                getattr(response, "headers", {}).get("Content-Type", "")
                if response is not None
                else ""
            )[:160],
            content_encoding=str(
                getattr(response, "headers", {}).get("Content-Encoding", "")
                if response is not None
                else ""
            )[:80],
            retryable=retryable,
        )
        material = _error_hash_material(
            market=market,
            announcement_item=announcement_item,
            start_date=start_date,
            end_date=end_date,
            error_code=error_code,
        )
        return MOPSQueryResult(
            market=market,
            announcement_item=announcement_item,
            rows=(),
            response_sha256=sha256(material.encode("utf-8")).hexdigest(),
            source_status="error",
            error_code=error_code,
            query_start_date=start_date,
            query_end_date=end_date,
            attempt_count=1,
            attempts=(attempt,),
        )


def _error_hash_material(
    *,
    market: str,
    announcement_item: str,
    start_date: date,
    end_date: date,
    error_code: str,
) -> str:
    """維持歷史 error response_sha256 的 synthetic context hash 語意。"""

    return json.dumps(
        {
            "market": market,
            "announcement_item": announcement_item,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "error_code": error_code,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _query_with_retries(
    session: requests.Session,
    *,
    market: str,
    announcement_item: str,
    start_date: date,
    end_date: date,
    timeout_seconds: int,
    max_retries: int,
    raw_failure_receipt_root: Path | None = None,
    capture_success_entity: bool = False,
) -> MOPSQueryResult:
    if not 0 <= max_retries <= 1:
        raise ValueError("max_retries must be between 0 and 1 (at most 2 total attempts)")
    retry_errors: list[str] = []
    last_result: MOPSQueryResult | None = None
    attempt_lineage: list[MOPSQueryAttempt] = []
    for attempt in range(max_retries + 1):
        result = _safe_query(
            session,
            market=market,
            announcement_item=announcement_item,
            start_date=start_date,
            end_date=end_date,
            timeout_seconds=timeout_seconds,
            attempt_number=attempt + 1,
            capture_success_entity=capture_success_entity,
        )
        last_result = result
        if result.source_status != "error":
            attempt_lineage.extend(result.attempts)
            return replace(
                result,
                attempt_count=attempt + 1,
                retry_error_codes=tuple(retry_errors),
                attempts=tuple(attempt_lineage),
            )
        failed_attempts = list(result.attempts)
        if raw_failure_receipt_root is not None:
            failed_attempts = [
                _write_failure_prefix_receipt(
                    raw_failure_receipt_root,
                    item,
                    market=market,
                    announcement_item=announcement_item,
                    start_date=start_date,
                    end_date=end_date,
                )
                for item in failed_attempts
            ]
        attempt_lineage.extend(failed_attempts)
        if not _is_retryable(result) or attempt >= max_retries:
            break
        if result.error_code:
            retry_errors.append(result.error_code)
    assert last_result is not None
    return replace(
        last_result,
        attempt_count=len(attempt_lineage) if attempt_lineage else min(max_retries + 1, attempt + 1),
        retry_error_codes=tuple(retry_errors),
        attempts=tuple(attempt_lineage),
    )


def _is_retryable(result: MOPSQueryResult) -> bool:
    if result.attempts:
        return result.attempts[-1].retryable
    # 相容由測試／離線 fixture 建立、尚未帶逐次 attempt receipt 的結果。
    return result.error_code in {
        "network_timeout",
        "network_error",
        "invalid_json",
        "response_read_error",
        "http_transport_error",
    }


def _write_failure_prefix_receipt(
    receipt_root: Path,
    attempt: MOPSQueryAttempt,
    *,
    market: str,
    announcement_item: str,
    start_date: date,
    end_date: date,
) -> MOPSQueryAttempt:
    """只寫最多 64 KiB 的失敗 response prefix；已存在檔案永不覆寫。"""

    if not attempt.raw_body_prefix:
        return attempt
    receipt_root = Path(receipt_root)
    receipt_root.mkdir(parents=True, exist_ok=True)
    if receipt_root.is_symlink():
        raise OSError(f"MOPS failure prefix directory must not be a symlink: {receipt_root}")
    filename = (
        f"mops_{market}_{announcement_item}_{start_date.isoformat()}_"
        f"{end_date.isoformat()}_attempt_{attempt.attempt_number}.body.prefix"
    )
    path = receipt_root / filename
    if path.resolve().parent != receipt_root.resolve():
        raise OSError(f"MOPS failure prefix path escapes its receipt directory: {path}")
    with path.open("xb") as handle:
        handle.write(attempt.raw_body_prefix)
        handle.flush()
    prefix_sha256 = sha256(attempt.raw_body_prefix).hexdigest()
    if sha256(path.read_bytes()).hexdigest() != prefix_sha256:
        raise OSError(f"MOPS failure prefix receipt hash mismatch: {path}")
    return replace(
        attempt,
        raw_body_prefix_path=f"raw_failed_attempts/{filename}",
    )


def _iter_date_windows(
    start_date: date,
    end_date: date,
    *,
    window_days: int,
) -> tuple[tuple[date, date], ...]:
    if end_date < start_date:
        raise ValueError("end_date must not be earlier than start_date")
    if not 1 <= window_days <= 31:
        raise ValueError("window_days must be between 1 and 31")
    windows: list[tuple[date, date]] = []
    cursor = start_date
    while cursor <= end_date:
        window_end = min(end_date, cursor + timedelta(days=window_days - 1))
        windows.append((cursor, window_end))
        cursor = window_end + timedelta(days=1)
    return tuple(windows)


def _parse_choices(raw: str, allowed: set[str], label: str) -> tuple[str, ...]:
    values = tuple(dict.fromkeys(part.strip() for part in raw.split(",") if part.strip()))
    invalid = sorted(set(values) - allowed)
    if not values or invalid:
        raise ValueError(f"invalid {label}: {','.join(invalid) if invalid else 'empty'}")
    return values


def _safe_output_path(root: Path, name: str) -> Path:
    if not name or Path(name).name != name:
        raise ValueError("output filename must be a plain filename")
    candidate = (root / name).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise ValueError("output path must remain under output root")
    return candidate


if __name__ == "__main__":
    raise SystemExit(main())
