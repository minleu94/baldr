#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Background job: fetch TWSE + TPEX daily prices, sync SQLite, and recalculate technical indicators."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app_module.update_service import UpdateService
from data_module.config import TWStockConfig
from data_module.recommendation_calibration_source_contract import (
    build_technical_computation_evidence,
    capture_technical_input_snapshot,
    publish_technical_indicator_receipt,
    reuse_verified_technical_computation_receipt,
)


def _write_state(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = datetime.now().isoformat(timespec="seconds")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _cancel_requested(cancel_file: Path | None) -> bool:
    """只以本次工作明確提供的 marker 請求合作式停止。"""

    return cancel_file is not None and cancel_file.exists()


def _step(name: str, ok: bool, message: str, rows: int = 0, warnings: List[str] | None = None) -> Dict[str, Any]:
    return {
        "name": name,
        "status": "done" if ok else "failed",
        "message": message,
        "rows": rows,
        "warnings": warnings or [],
    }


def _tpex_warning_messages(result: Dict[str, Any]) -> List[str]:
    messages = [str(item) for item in result.get("warnings", []) if str(item).strip()]
    failed_dates = sorted({str(item) for item in result.get("failed_dates", []) if str(item).strip()})
    if failed_dates:
        messages.append(f"TPEX 每日股價缺少日期：{', '.join(failed_dates)}")
    return list(dict.fromkeys(messages))


def _parse_status_date(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _should_skip_technical_indicators(
    status: Dict[str, Any],
    *,
    force_all: bool,
    technical_coverage: Dict[str, Any] | None = None,
) -> tuple[bool, str]:
    if force_all:
        return False, ""

    if technical_coverage and technical_coverage.get("success") and not technical_coverage.get("is_current", True):
        covered = technical_coverage.get("covered_stock_count", 0)
        eligible = technical_coverage.get("eligible_stock_count", 0)
        latest = technical_coverage.get("daily_latest_date") or "latest daily date"
        return False, f"技術指標最新日覆蓋不足（{latest}：{covered}/{eligible}），執行增量計算"

    daily_latest = _parse_status_date((status.get("daily_data") or {}).get("latest_date"))
    technical_latest = _parse_status_date((status.get("technical_indicators") or {}).get("latest_date"))
    if daily_latest and technical_latest and technical_latest >= daily_latest:
        latest_text = technical_latest.strftime("%Y-%m-%d")
        return True, f"技術指標已是最新（{latest_text}），跳過增量計算"
    return False, ""


def _run_tpex_parallel(
    service: UpdateService,
    config: TWStockConfig,
    state_file: Path,
    state: Dict[str, Any],
    *,
    start_date: str,
    end_date: str,
    workers: int,
    cancel_callback=None,
) -> Dict[str, Any]:
    date_keys = service._iter_weekday_date_keys(start_date, end_date)
    source = service._create_tpex_daily_price_source()
    pending_dates = [
        date_key
        for date_key in date_keys
        if not (config.tpex_daily_price_dir / f"{date_key}.csv").exists()
    ]
    skipped_dates = [date_key for date_key in date_keys if date_key not in pending_dates]
    updated_dates: list[str] = []
    failed_dates: list[str] = []
    fallback_dates: list[str] = []
    total_rows = 0
    total_skipped_rows = 0
    total = len(pending_dates)
    cancellation_seen = False

    if total == 0:
        return {
            "success": True,
            "message": "TPEX daily price CSV already complete for requested range",
            "requested_dates": date_keys,
            "updated_dates": [],
            "fallback_dates": [],
            "skipped_dates": skipped_dates,
            "failed_dates": [],
            "tpex_rows": 0,
            "skipped_rows": 0,
            "diagnostic_count": 0,
            "source_dates": [],
        }

    if cancel_callback is not None and cancel_callback():
        return {
            "success": False,
            "cancelled": True,
            "message": "TPEX 平行更新已合作式取消（尚未開始）",
            "requested_dates": date_keys,
            "updated_dates": [],
            "fallback_dates": [],
            "skipped_dates": skipped_dates,
            "failed_dates": [],
            "tpex_rows": 0,
            "skipped_rows": 0,
            "diagnostic_count": 0,
            "source_dates": [],
        }

    def fetch_one(date_key: str) -> Dict[str, Any]:
        result = source.update_for_date(date_key)
        return {
            "requested_date": date_key,
            "success": result.success,
            "source_date": result.source_date or date_key,
            "row_count": int(result.row_count),
            "skipped_count": int(result.skipped_count),
            "message": result.message,
        }

    completed = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_map = {executor.submit(fetch_one, date_key): date_key for date_key in pending_dates}
        for future in as_completed(future_map):
            requested_date = future_map[future]
            if future.cancelled():
                continue
            try:
                result = future.result()
            except Exception as exc:
                failed_dates.append(requested_date)
                result = {"row_count": 0, "skipped_count": 0, "message": str(exc), "source_date": None}

            if result.get("success"):
                source_date = str(result.get("source_date") or requested_date)
                updated_dates.append(source_date)
                total_rows += int(result.get("row_count", 0))
                if source_date != requested_date:
                    fallback_dates.append(source_date)
            else:
                failed_dates.append(requested_date)
            total_skipped_rows += int(result.get("skipped_count", 0))
            completed += 1

            if cancel_callback is not None and cancel_callback():
                # 已送出的 HTTP request 讓它在自己的有限 timeout 內完成；
                # 不再提交後續日期，且保留已完成的結果供狀態檔追蹤。
                cancellation_seen = True
                for pending in future_map:
                    if not pending.done():
                        pending.cancel()

            if completed == total or completed % 10 == 0:
                state["steps"]["tpex_daily"] = {
                    "status": "running",
                    "message": (
                        f"running {completed}/{total}; "
                        f"updated={len(set(updated_dates))}, failed={len(set(failed_dates))}, skipped={len(skipped_dates)}"
                    ),
                    "rows": len(set(updated_dates)),
                    "warnings": [],
                }
                state["tpex_progress"] = {
                    "completed": completed,
                    "total": total,
                    "workers": workers,
                    "updated": len(set(updated_dates)),
                    "failed": len(set(failed_dates)),
                    "skipped_existing": len(skipped_dates),
                }
                _write_state(state_file, state)

    unique_updated_dates = sorted(set(updated_dates))
    unique_failed_dates = sorted(set(failed_dates))
    if cancellation_seen or (cancel_callback is not None and cancel_callback()):
        return {
            "success": False,
            "cancelled": True,
            "message": "TPEX 平行更新已合作式取消（已完成目前安全邊界）",
            "requested_dates": date_keys,
            "updated_dates": unique_updated_dates,
            "fallback_dates": sorted(set(fallback_dates)),
            "skipped_dates": sorted(set(skipped_dates)),
            "failed_dates": unique_failed_dates,
            "tpex_rows": total_rows,
            "skipped_rows": total_skipped_rows,
            "diagnostic_count": 0,
            "source_dates": unique_updated_dates,
        }
    warnings = _tpex_warning_messages({"failed_dates": unique_failed_dates})
    has_any_local_data = bool(unique_updated_dates or skipped_dates)
    return {
        "success": has_any_local_data and not unique_failed_dates,
        "message": (
            f"TPEX 每日股價區間更新未完整：缺少日期 {', '.join(unique_failed_dates)}"
            if unique_failed_dates
            else "TPEX 每日股價區間更新完成"
            if has_any_local_data
            else "TPEX 每日股價區間更新失敗：無可寫入日期"
        ),
        "requested_dates": date_keys,
        "updated_dates": unique_updated_dates,
        "fallback_dates": sorted(set(fallback_dates)),
        "skipped_dates": sorted(set(skipped_dates)),
        "failed_dates": unique_failed_dates,
        "warnings": warnings,
        "tpex_rows": total_rows,
        "skipped_rows": total_skipped_rows,
        "diagnostic_count": 0,
        "source_dates": unique_updated_dates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TPEX background refresh + technical indicators.")
    parser.add_argument("--start-date", required=True, help="開始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="結束日期 YYYY-MM-DD")
    parser.add_argument("--state-file", required=True, help="背景狀態 JSON 檔路徑")
    parser.add_argument("--delay-seconds", type=float, default=1.0)
    parser.add_argument("--sync-sqlite", action="store_true")
    parser.add_argument("--twse-update", action="store_true")
    parser.add_argument("--technical-force-all", action="store_true")
    parser.add_argument("--tpex-workers", type=int, default=1)
    parser.add_argument(
        "--cancel-file",
        default=None,
        help="可選合作式取消 marker；只在安全的日期／寫入邊界停止",
    )
    args = parser.parse_args()

    state_file = Path(args.state_file)
    cancel_file = Path(args.cancel_file).expanduser() if args.cancel_file else None
    state: Dict[str, Any] = {
        "status": "running",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "tpex_full_refresh_and_technical",
        "start_date": args.start_date,
        "end_date": args.end_date,
        "steps": {
            "twse_daily": {"status": "pending", "message": "waiting", "rows": 0, "warnings": []},
            "tpex_daily": {"status": "pending", "message": "waiting", "rows": 0, "warnings": []},
            "sqlite": {"status": "pending", "message": "waiting", "rows": 0, "warnings": []},
            "technical": {"status": "pending", "message": "waiting", "rows": 0, "warnings": []},
        },
        "cancel_file": str(cancel_file) if cancel_file is not None else None,
        "cancel_requested": False,
        "cancel_completed": False,
    }
    _write_state(state_file, state)

    def cancellation_requested() -> bool:
        return _cancel_requested(cancel_file)

    def finish_cancelled(message: str) -> int:
        state["status"] = "cancelled"
        state["cancel_requested"] = True
        state["cancel_completed"] = True
        state["message"] = message
        _write_state(state_file, state)
        return 0

    # keep data-root stable for this job
    data_root = os.environ.get("DATA_ROOT")
    if data_root:
        os.environ["DATA_ROOT"] = data_root

    config = TWStockConfig()
    service = UpdateService(config)
    all_warnings: List[str] = []
    sync_rows = 0
    twse_result: Dict[str, Any] = {}
    technical_result: Dict[str, Any] = {
        "success": False,
        "message": "技術指標尚未執行",
    }
    technical_step_status = "failed"

    try:
        if args.twse_update:
            state["steps"]["twse_daily"] = {"status": "running", "message": "running", "rows": 0, "warnings": []}
            _write_state(state_file, state)

            twse_result = service.update_daily(
                args.start_date,
                args.end_date,
                delay_seconds=args.delay_seconds,
                cancel_callback=cancellation_requested,
            )
            state["steps"]["twse_daily"] = _step(
                "twse_daily",
                bool(twse_result.get("success", False)),
                twse_result.get("message", "TWSE 每日股價更新完成"),
                rows=len(twse_result.get("updated_dates", [])),
            )
            if not twse_result.get("success", False):
                all_warnings.append(f"TWSE 每日股價更新失敗：{twse_result.get('message', 'unknown')}")
            _write_state(state_file, state)
            if twse_result.get("cancelled"):
                return finish_cancelled(
                    str(twse_result.get("message") or "TWSE 更新已合作式取消")
                )
        else:
            state["steps"]["twse_daily"] = {
                "status": "skipped",
                "message": "已跳過 TWSE 更新（未指定 --twse-update）",
                "rows": 0,
                "warnings": [],
            }
            _write_state(state_file, state)

        state["steps"]["tpex_daily"] = {"status": "running", "message": "running", "rows": 0, "warnings": []}
        _write_state(state_file, state)
        if args.tpex_workers > 1:
            tpex_result = _run_tpex_parallel(
                service,
                config,
                state_file,
                state,
                start_date=args.start_date,
                end_date=args.end_date,
                workers=args.tpex_workers,
                cancel_callback=cancellation_requested,
            )
        else:
            tpex_result = service.update_tpex_daily_price_range(
                args.start_date,
                args.end_date,
                delay_seconds=args.delay_seconds,
                force_refresh=False,
                break_on_repeated_source_date=False,
                sync_to_sqlite=False,
                cancel_callback=cancellation_requested,
            )
        state["steps"]["tpex_daily"] = _step(
            "tpex_daily",
            bool(tpex_result.get("success", False)),
            tpex_result.get("message", "TPEX 每日股價更新完成"),
            rows=len(tpex_result.get("updated_dates", [])),
            warnings=(list(tpex_result.get("warnings", [])) if tpex_result.get("warnings") else []),
        )
        all_warnings.extend(_tpex_warning_messages(tpex_result))
        if not tpex_result.get("success", False):
            all_warnings.append(f"TPEX 每日股價更新失敗：{tpex_result.get('message', 'unknown')}")
        state["tpex_updated_dates"] = tpex_result.get("updated_dates", [])
        state["tpex_fallback_dates"] = tpex_result.get("fallback_dates", [])
        state["tpex_skipped_dates"] = tpex_result.get("skipped_dates", [])
        _write_state(state_file, state)
        if tpex_result.get("cancelled"):
            return finish_cancelled(
                str(tpex_result.get("message") or "TPEX 更新已合作式取消")
            )

        if args.sync_sqlite:
            if cancellation_requested():
                return finish_cancelled("已取消：尚未開始 SQLite 同步")
            state["steps"]["sqlite"] = {"status": "running", "message": "running", "rows": 0, "warnings": []}
            _write_state(state_file, state)
            sync_result = service.sync_source_to_sqlite(
                "daily_price_files",
                args.start_date,
                args.end_date,
                cancel_callback=cancellation_requested,
            )
            sync_rows = int(sync_result.get("synced_records", 0))
            state["steps"]["sqlite"] = _step(
                "sqlite",
                bool(sync_result.get("success", False)),
                sync_result.get("message", "SQLite 同步完成"),
                rows=sync_rows,
            )
            if not sync_result.get("success", False):
                all_warnings.append(f"SQLite 同步失敗：{sync_result.get('message', 'unknown')}")
            _write_state(state_file, state)
            if sync_result.get("cancelled"):
                return finish_cancelled(
                    str(sync_result.get("message") or "SQLite 同步已合作式取消")
                )
        else:
            state["steps"]["sqlite"] = {
                "status": "skipped",
                "message": "已跳過 SQLite 同步（未指定 --sync-sqlite）",
                "rows": 0,
                "warnings": [],
            }
            _write_state(state_file, state)

        if cancellation_requested():
            return finish_cancelled("已取消：尚未開始技術指標計算")
        status = service.check_data_overview() if hasattr(service, "check_data_overview") else service.check_data_status()
        technical_coverage = service.check_technical_indicator_latest_coverage()
        source_dates = [
            str(value).strip()
            for value in tpex_result.get("source_dates", [])
            if str(value).strip()
        ]
        evidence_start = min(source_dates) if source_dates else args.start_date
        evidence_end = max(source_dates) if source_dates else args.end_date
        should_skip_technical, skip_message = _should_skip_technical_indicators(
            status,
            force_all=args.technical_force_all,
            technical_coverage=technical_coverage,
        )
        if should_skip_technical:
            technical_step_status = "skipped"
            technical_result = {
                "success": True,
                "skipped": True,
                "skip_reason": "technical_indicators_current",
                "message": skip_message,
            }
            reuse_result = reuse_verified_technical_computation_receipt(
                authorized_output_roots=(config.output_root,),
                source_db=config.db_file,
                source_date_start=evidence_start,
                source_date_end=evidence_end,
                availability_cutoff_at=datetime.now(timezone.utc),
            )
            if reuse_result.get("status") == "reused":
                technical_result.update(
                    {
                        "technical_reuse_status": "reused",
                        "technical_computation": reuse_result.get(
                            "technical_computation"
                        ),
                        "technical_computation_reuse": reuse_result.get(
                            "source_publication_receipt"
                        ),
                    }
                )
            else:
                # currentity skip 沒有新計算 witness 時，不以本次 checked clock
                # 偽造新的 technical availability；只有已驗證的舊 receipt 可重用。
                technical_result.update(
                    {
                        "technical_reuse_status": "not_found",
                        "technical_reuse_reason": str(
                            reuse_result.get("reason") or "not_found"
                        ),
                        "technical_reuse_diagnostics": reuse_result.get(
                            "diagnostics", []
                        ),
                    }
                )
            state["steps"]["technical"] = {
                "status": "skipped",
                "message": skip_message,
                "rows": 0,
                "warnings": [],
            }
            _write_state(state_file, state)
        else:
            state["steps"]["technical"] = {"status": "running", "message": "running", "rows": 0, "warnings": []}
            _write_state(state_file, state)
            calculation_started_at = datetime.now(timezone.utc)
            input_snapshot = capture_technical_input_snapshot(
                config.db_file,
                source_date_start=evidence_start,
                source_date_end=evidence_end,
            )
            tech_result = service.calculate_technical_indicators(
                target_stock=None,
                force_all=args.technical_force_all,
                start_date=None,
                progress_callback=None,
                cancel_callback=cancellation_requested,
                incremental_lookback_days=120,
            )
            technical_result = dict(tech_result)
            technical_step_status = (
                "passed" if tech_result.get("success", False) else "failed"
            )
            if tech_result.get("success") is True and input_snapshot.get("verified") is True:
                try:
                    technical_result["technical_computation"] = (
                        build_technical_computation_evidence(
                            source_db=config.db_file,
                            calculation_result=technical_result,
                            source_date_start=evidence_start,
                            source_date_end=evidence_end,
                            started_at=calculation_started_at,
                            completed_at=datetime.now(timezone.utc),
                            input_snapshot=input_snapshot,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    # 計算結果仍保留，但沒有完整 witness 時不得發佈 receipt。
                    technical_result["technical_computation_error"] = (
                        f"{type(exc).__name__}:{exc}"
                    )
            elif tech_result.get("success") is True:
                technical_result["technical_computation_error"] = str(
                    input_snapshot.get("reason")
                    or "technical_input_snapshot_unverified"
                )
            tech_stocks = tech_result.get("updated_stocks", [])
            tech_rows = len(tech_stocks) if isinstance(tech_stocks, list) else 0
            state["steps"]["technical"] = _step(
                "technical",
                bool(tech_result.get("success", False)),
                tech_result.get("message", "技術指標計算完成"),
                rows=tech_rows,
            )
            if not tech_result.get("success", False):
                all_warnings.append(f"技術指標計算失敗：{tech_result.get('message', 'unknown')}")
            if tech_result.get("cancelled"):
                return finish_cancelled(
                    str(tech_result.get("message") or "技術指標計算已合作式取消")
                )
        _write_state(state_file, state)

        publication_completed_at = datetime.now(timezone.utc)
        technical_reuse_verified = (
            technical_step_status == "passed"
            or technical_result.get("technical_reuse_status") == "reused"
        )
        publication_status = {
            "status": (
                "passed"
                if bool(tpex_result.get("success"))
                and (not args.twse_update or bool(twse_result.get("success")))
                and technical_reuse_verified
                and technical_result.get("success") is True
                else "failed"
            ),
            "run_id": "tpex-full-refresh-"
            + publication_completed_at.strftime("%Y%m%dT%H%M%S%fZ"),
            "started_at": state.get("started_at"),
            "completed_at": publication_completed_at.isoformat(),
            "start_date": args.start_date,
            "end_date": args.end_date,
            "writes_market_data_db": bool(args.sync_sqlite),
            "steps": [
                *(
                    [
                        {
                            "name": "update_twse_daily_prices",
                            "status": (
                                "passed"
                                if twse_result.get("success")
                                else "failed"
                            ),
                            "result": twse_result,
                        }
                    ]
                    if args.twse_update
                    else []
                ),
                {
                    "name": "update_tpex_daily_prices",
                    "status": (
                        "passed" if tpex_result.get("success") else "failed"
                    ),
                    "result": tpex_result,
                },
                {
                    "name": "calculate_technical_indicators",
                    "status": technical_step_status,
                    "result": technical_result,
                },
            ],
        }
        if (
            technical_step_status == "skipped"
            and technical_result.get("technical_reuse_status") != "reused"
        ):
            state["technical_publication_receipt"] = {
                "status": "blocked",
                "reason": "technical_computation_reuse_missing",
                "reuse_reason": technical_result.get("technical_reuse_reason"),
                "reuse_diagnostics": technical_result.get(
                    "technical_reuse_diagnostics", []
                )
            }
            all_warnings.append(
                "technical publication receipt blocked: "
                "technical_computation_reuse_missing"
            )
        else:
            try:
                state["technical_publication_receipt"] = (
                    publish_technical_indicator_receipt(
                        output_root=config.output_root,
                        source_db=config.db_file,
                        update_status=publication_status,
                        authorized_output_roots=(config.output_root,),
                    )
                )
                if state["technical_publication_receipt"].get("status") != "published":
                    all_warnings.append(
                        "technical publication receipt blocked: "
                        + str(
                            state["technical_publication_receipt"].get("reason")
                            or "unknown"
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                # receipt 是來源證明；寫入失敗只能保留診斷，不能改變資料更新結果。
                state["technical_publication_receipt"] = {
                    "status": "blocked",
                    "reason": f"technical_publication_receipt_failed:{type(exc).__name__}",
                    "error": str(exc),
                }
                all_warnings.append(
                    "technical publication receipt blocked: "
                    + str(state["technical_publication_receipt"]["reason"])
                )

        all_warnings = list(dict.fromkeys(all_warnings))
        state["status"] = "done" if not all_warnings else "done_with_warning"
        state["warnings"] = all_warnings
        state["sqlite_synced_rows"] = sync_rows
        _write_state(state_file, state)
        return 0
    except Exception as exc:  # pragma: no cover - 防護性異常寫入
        state["status"] = "failed"
        state["message"] = f"背景任務執行失敗：{exc}"
        state["steps"] = state.get("steps", {})
        _write_state(state_file, state)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
