"""唯讀驗收已保存的基本面研究捕捉；不把捕捉升格為正式資料更新。"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
import os
from pathlib import Path, PurePosixPath
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_module.mops_quarterly_openapi_research_capture import verify_capture_run
from data_module.scheduled_research_acquisition_binding import (
    quick_monthly_capture_status,
    verify_weekly_acquisition,
)


def _quick_status_snapshot(**kwargs: Any) -> Any:
    # Defer shared-module loading so an in-progress edit becomes a blocked
    # receipt instead of preventing the audit from reporting its own result.
    from scripts.scheduled.data_freshness_probe import _quick_status_snapshot as read
    return read(**kwargs)


def _read_bounded_regular_file(path: Path, *, max_bytes: int) -> bytes:
    from scripts.scheduled.data_freshness_probe import _read_bounded_regular_file as read
    return read(path, max_bytes=max_bytes)


def _strict_json_loads(raw: bytes) -> Any:
    from scripts.scheduled.data_freshness_probe import _strict_json_loads as read
    return read(raw)

MAX_METADATA_BYTES = 16 * 1024 * 1024
MAX_ENTITY_BYTES = 32 * 1024 * 1024
MONTHLY_URLS = {
    "twse": "https://openapi.twse.com.tw/v1/opendata/t187ap05_L",
    "tpex": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O",
}


def _object(path: Path) -> tuple[dict[str, Any], str]:
    raw = _read_bounded_regular_file(path, max_bytes=MAX_METADATA_BYTES)
    value = _strict_json_loads(raw)
    if not isinstance(value, dict):
        raise ValueError("receipt_must_be_object")
    return value, hashlib.sha256(raw).hexdigest()


def _member(root: Path, value: object) -> Path:
    if not isinstance(value, str) or "\\" in value:
        raise ValueError("invalid_artifact_relative_path")
    relative = PurePosixPath(value)
    if relative.is_absolute() or not relative.parts or any(p in {"..", "."} or ":" in p for p in relative.parts):
        raise ValueError("artifact_path_escape")
    return root.joinpath(*relative.parts)


def audit_monthly(quick_path: Path, *, now: datetime) -> dict[str, Any]:
    """沿已驗證的Quick終端身分讀回其獨立子收據與完整原件。"""
    parent, binding = _quick_status_snapshot(
        status_path=quick_path, canonical_status_path=quick_path, observed_at=now,
    )
    if parent is None or binding.get("binding_status") != "verified":
        raise ValueError("quick_parent_terminal_identity_not_verified")
    declaration = parent.get("monthly_revenue_research_capture")
    if not isinstance(declaration, dict) or not declaration.get("result_receipt_path"):
        return {"status": "not_recorded", "parent_run_id": parent.get("run_id"), "reason": "monthly_child_receipt_not_declared"}
    child_path = Path(declaration["result_receipt_path"])
    child, child_sha = _object(child_path)
    if child.get("schema_version") != "scheduled-monthly-revenue-research-capture.v1":
        raise ValueError("monthly_child_schema_mismatch")
    if child.get("run_id") != parent.get("run_id") or child.get("core_status") != parent.get("status"):
        raise ValueError("monthly_parent_child_identity_mismatch")
    if Path(str(child.get("core_status_path"))).resolve() != quick_path.resolve():
        raise ValueError("monthly_parent_path_mismatch")
    capture = child.get("research_capture")
    if not isinstance(capture, dict):
        raise ValueError("monthly_child_result_missing")
    if capture.get("status") != "captured":
        return {"status": "failed", "parent_run_id": parent["run_id"], "child_sha256": child_sha, "reason": capture.get("reason", "monthly_capture_not_completed")}
    result = capture.get("result")
    if not isinstance(result, dict) or result.get("schema_version") != "monthly-revenue-research-candidate-status.v1" or result.get("status") != "captured":
        raise ValueError("monthly_capture_result_schema_mismatch")
    root = Path(result["run_root"])
    manifest, manifest_sha = _object(_member(root, result["candidate_manifest_file"]))
    if manifest_sha != result.get("candidate_manifest_sha256"):
        raise ValueError("monthly_manifest_hash_mismatch")
    if manifest.get("schema_version") != "monthly-revenue-research-candidate.v1" or manifest.get("status") != "research_only_candidate_created":
        raise ValueError("monthly_manifest_schema_mismatch")
    if manifest.get("run_id") != result.get("run_id") or manifest.get("candidate_period") != result.get("candidate_period"):
        raise ValueError("monthly_capture_manifest_identity_mismatch")
    for flag in ("auto_apply", "formal_apply_authorized", "historical_pit_credit", "writes_formal_data", "writes_formal_database"):
        if manifest.get(flag) is not False:
            raise ValueError("monthly_qualification_boundary_changed:" + flag)
    readback = manifest.get("readback")
    if not isinstance(readback, dict):
        raise ValueError("monthly_readback_missing")
    files = readback.get("files")
    required = {manifest.get("candidate_file"), manifest.get("availability_file"), "source/capture_run.json", "full_source_scope_manifest.json", "source/twse.json", "source/tpex.json"}
    if not isinstance(files, dict) or None in required or not required.issubset(files):
        raise ValueError("monthly_custody_inventory_incomplete")
    for relative, pin in files.items():
        if not isinstance(pin, dict):
            raise ValueError("monthly_artifact_pin_invalid")
        raw = _read_bounded_regular_file(_member(root, relative), max_bytes=MAX_ENTITY_BYTES)
        if len(raw) != pin.get("bytes") or hashlib.sha256(raw).hexdigest() != pin.get("sha256"):
            raise ValueError("monthly_artifact_hash_mismatch:" + relative)
    sources = result.get("source_results")
    if not isinstance(sources, dict) or set(sources) != {"twse", "tpex"}:
        raise ValueError("monthly_market_scope_incomplete")
    for venue, source in sources.items():
        if not isinstance(source, dict):
            raise ValueError("monthly_source_result_invalid")
        if source.get("requested_url") != MONTHLY_URLS[venue] or source.get("http_status") != 200 or source.get("status") != "captured":
            raise ValueError("monthly_source_identity_or_status_mismatch")
        if source.get("content_sha256") != files["source/" + venue + ".json"]["sha256"]:
            raise ValueError("monthly_source_custody_hash_mismatch")
    return {
        "status": "captured_verified", "period": manifest["candidate_period"],
        "rows": manifest["source_row_count"], "run_id": result["run_id"],
        "parent_run_id": parent["run_id"], "parent_status_sha256": binding["status_sha256"],
        "child_path": str(child_path), "child_sha256": child_sha,
        "manifest_sha256": manifest_sha, "verified_artifact_count": len(files),
        "binding_scope": "parent_terminal_identity_and_child_artifact_hashes",
        "child_records_parent_sha256": False,
        "historical_pit_credit": False, "formal_database_updated": False,
    }


def audit_quarterly(terminal_path: Path) -> dict[str, Any]:
    """重驗既有collector；沒有weekly父收據時不宣稱自然Task身分相符。"""
    terminal, terminal_sha = _object(terminal_path)
    if terminal.get("schema_version") != "mops-quarterly-openapi-research-terminal.v1":
        raise ValueError("quarterly_terminal_schema_mismatch")
    if terminal.get("status") not in {"completed_observation_only", "completed_with_review_items"}:
        return {"status": "failed", "terminal_sha256": terminal_sha, "reason": terminal.get("status", "unknown")}
    if terminal.get("formal_pit_eligible") is not False or terminal.get("candidate_available_at") is not None:
        raise ValueError("quarterly_qualification_boundary_changed")
    verified = verify_capture_run(terminal_path.parent)
    if verified != terminal.get("readback") or verified.get("run_id") != terminal.get("run_id"):
        raise ValueError("quarterly_terminal_readback_mismatch")
    return {
        "status": "captured_with_review" if terminal["status"] == "completed_with_review_items" else "captured_verified",
        "run_id": terminal["run_id"], "terminal_path": str(terminal_path),
        "terminal_sha256": terminal_sha, "request_receipts_verified": verified["request_receipts_verified"],
        "raw_rows_rechecked": verified["numeric_rows_rechecked"], "preview_rows_rechecked": verified["preview_rows_rechecked"],
        "weekly_parent_binding": "not_recorded", "natural_task_execution_verified": False,
        "historical_pit_credit": False, "formal_database_updated": False,
    }


def audit_quick_monthly_capture(
    quick_status_path: Path,
    *,
    quick_payload: dict[str, Any] | None,
    quick_binding: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """在已驗證 Quick 終端上投影月營收 child 等待／失敗或完成狀態。"""
    state = quick_monthly_capture_status(
        quick_payload=quick_payload,
        quick_binding=quick_binding,
        quick_status_path=quick_status_path,
        now=now,
    )
    if state.get("status") != "receipt_present":
        return state
    try:
        result = audit_monthly(quick_status_path, now=now)
    except (OSError, ValueError, TypeError, KeyError, ImportError, SyntaxError) as exc:
        return {"status": "blocked", "reason": str(exc) or type(exc).__name__, "error_type": type(exc).__name__, "formal_credit": False}
    expected_parent_sha = str(quick_binding.get("status_sha256", ""))
    actual_parent_sha = str(result.get("parent_status_sha256", ""))
    if expected_parent_sha.startswith("sha256:"):
        expected_parent_sha = expected_parent_sha[7:]
    if actual_parent_sha.startswith("sha256:"):
        actual_parent_sha = actual_parent_sha[7:]
    if not expected_parent_sha or expected_parent_sha != actual_parent_sha:
        return {"status": "blocked", "reason": "quick_parent_changed_during_child_audit", "formal_credit": False}
    return {**result, "formal_credit": False}


def _weekly_output_root(*, quick_status_path: Path, explicit_output_root: Path | None) -> Path:
    """由明確 root 或標準 Quick 路徑推回 weekly locator 所屬的 OUTPUT_ROOT。"""
    if explicit_output_root is not None:
        return Path(os.path.abspath(os.fspath(explicit_output_root)))
    quick_path = Path(os.path.abspath(os.fspath(quick_status_path)))
    if (
        quick_path.name != "latest_status.json"
        or quick_path.parent.name.casefold() != "data_update_quick"
        or quick_path.parent.parent.name.casefold() != "scheduled"
    ):
        raise ValueError("weekly_output_root_requires_explicit_root_or_canonical_quick_path")
    return quick_path.parent.parent.parent


def main(argv: list[str] | None = None) -> int:
    _configure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick-status", type=Path, required=True)
    parser.add_argument("--quarterly-terminal", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--weekly-parent-receipt-path", type=Path)
    parser.add_argument("--weekly-parent-receipt-sha256")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    report: dict[str, Any] = {"schema_version": "scheduled-research-acquisition-audit.v1", "checked_at": now.isoformat(), "read_only_sources": True, "database_write_performed": False, "formal_credit": False, "sources": {}}
    def audit_quick_monthly() -> dict[str, Any]:
        parent, parent_binding = _quick_status_snapshot(
            status_path=args.quick_status,
            canonical_status_path=args.quick_status,
            observed_at=now,
        )
        return audit_quick_monthly_capture(
            args.quick_status,
            quick_payload=parent,
            quick_binding=parent_binding,
            now=now,
        )

    actions = [("monthly", audit_quick_monthly)]
    if args.quarterly_terminal is not None:
        actions.append(("quarterly", lambda: audit_quarterly(args.quarterly_terminal)))
    for name, action in actions:
        try:
            report["sources"][name] = action()
        except (OSError, ValueError, TypeError, KeyError, ImportError, SyntaxError) as exc:
            report["sources"][name] = {"status": "blocked", "error_type": type(exc).__name__, "reason": str(exc)}
    if args.output_root is not None or args.weekly_parent_receipt_path is not None or args.weekly_parent_receipt_sha256 is not None:
        try:
            weekly_root = _weekly_output_root(
                quick_status_path=args.quick_status,
                explicit_output_root=args.output_root,
            )
        except (OSError, ValueError, TypeError) as exc:
            report["sources"]["weekly_collection"] = {
                "status": "blocked",
                "reason": str(exc) or type(exc).__name__,
                "error_type": type(exc).__name__,
                "formal_credit": False,
            }
        else:
            report["sources"]["weekly_collection"] = verify_weekly_acquisition(
                weekly_root,
                now=now,
                receipt_path=args.weekly_parent_receipt_path,
                expected_sha256=args.weekly_parent_receipt_sha256,
            )
    failed = any(s["status"] in {"failed", "blocked"} for s in report["sources"].values())
    partial = any(s["status"] == "partial" for s in report["sources"].values())
    report["status"] = "blocked" if failed else "partial" if partial else "observed"
    rendered = json.dumps(report, ensure_ascii=True, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf8")
    print(rendered, end="")
    return 2 if report["status"] in {"blocked", "partial"} else 0


def _configure_utf8_stdio() -> None:
    """在 Windows CP1252 主控台輸出繁體中文 help 與唯讀查核結果。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except (OSError, ValueError):
                pass


if __name__ == "__main__":
    raise SystemExit(main())
