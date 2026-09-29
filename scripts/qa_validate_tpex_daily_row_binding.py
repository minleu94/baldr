"""Validate current quick-run TPEx rows inside one isolated QA root."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_module.qa_tpex_daily_row_binding import (  # noqa: E402
    TpexRowBindingError,
    publish_row_binding_receipt,
    verify_tpex_daily_row_binding,
)


QA_PARENT = REPO_ROOT / "output" / "qa"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "唯讀核對指定 quick run 的 TPEx custody → 當日 CSV → 隔離 QA daily_prices；"
            "不會啟動 updater 或寫入 SQLite。"
        )
    )
    parser.add_argument("--qa-root", required=True, help="output/qa 下的單一隔離 QA root")
    parser.add_argument(
        "--terminal-status",
        required=True,
        help="該次 quick run 的 terminal status JSON 絕對路徑（不得使用隱含 latest）",
    )
    parser.add_argument("--expected-run-id", required=True, help="要綁定的 quick run_id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")
    args = _build_parser().parse_args(argv)
    try:
        qa_root = Path(args.qa_root)
        status_path = Path(args.terminal_status)
        if not qa_root.is_absolute() or not status_path.is_absolute():
            raise TpexRowBindingError("qa_root_and_terminal_status_must_be_absolute")
        _reject_reparse_components(qa_root)
        _reject_reparse_components(status_path)
        qa_root = qa_root.resolve(strict=True)
        expected_parent = QA_PARENT.resolve(strict=False)
        if qa_root.parent != expected_parent:
            raise TpexRowBindingError("qa_root_must_be_a_direct_output_qa_child")
        _assert_file_within(qa_root, status_path)
        status_before = status_path.stat()
        if status_before.st_size > 64 * 1024 * 1024:
            raise TpexRowBindingError("terminal_status_exceeds_64_mib_bound")
        status_bytes = status_path.read_bytes()
        status_after_read = status_path.stat()
        if (
            len(status_bytes) != status_before.st_size
            or status_before.st_size != status_after_read.st_size
            or status_before.st_mtime_ns != status_after_read.st_mtime_ns
        ):
            raise TpexRowBindingError("terminal_status_changed_while_reading")
        status_payload = json.loads(status_bytes.decode("utf-8-sig"))
        if not isinstance(status_payload, dict):
            raise TpexRowBindingError("terminal_status_must_be_json_object")
        if status_payload.get("run_id") != args.expected_run_id:
            raise TpexRowBindingError("terminal_status_run_id_does_not_match_pin")

        data_value = status_payload.get("data_root")
        output_value = status_payload.get("output_root")
        if not isinstance(data_value, str) or not isinstance(output_value, str):
            raise TpexRowBindingError("terminal_status_data_or_output_root_missing")
        data_root = Path(data_value)
        output_root = Path(output_value)
        if not data_root.is_absolute() or not output_root.is_absolute():
            raise TpexRowBindingError("terminal_status_roots_must_be_absolute")
        database_path = data_root / "sqlite" / "twstock.db"

        result = verify_tpex_daily_row_binding(
            status_payload,
            qa_root=qa_root,
            data_root=data_root,
            output_root=output_root,
            database_path=database_path,
        )
        status_after = status_path.stat()
        if (
            status_before.st_size != status_after.st_size
            or status_before.st_mtime_ns != status_after.st_mtime_ns
        ):
            raise TpexRowBindingError("terminal_status_changed_during_verification")
        result["quick_run"]["terminal_status_relative_path"] = status_path.resolve(
            strict=True
        ).relative_to(qa_root).as_posix()
        result["quick_run"]["terminal_status_sha256"] = (
            "sha256:" + hashlib.sha256(status_bytes).hexdigest()
        )
        receipt_path = publish_row_binding_receipt(
            result, qa_root=qa_root, output_root=output_root
        )
        print(
            json.dumps(
                {
                    "status": "verified",
                    "run_id": args.expected_run_id,
                    "receipt_path": str(receipt_path),
                    "date_count": result["date_count"],
                    "row_count": result["row_count"],
                    "ready_for_daily_pipeline": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        TpexRowBindingError,
        ValueError,
    ) as exc:
        print(
            json.dumps(
                {"status": "blocked", "reason": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


def _assert_file_within(root: Path, path: Path) -> None:
    _reject_reparse_components(path)
    try:
        resolved_root = root.resolve(strict=True)
        resolved_path = path.resolve(strict=True)
    except OSError as exc:
        raise TpexRowBindingError("terminal_status_path_unavailable") from exc
    if not resolved_path.is_file():
        raise TpexRowBindingError("terminal_status_not_regular_file")
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise TpexRowBindingError("terminal_status_outside_qa_root") from exc


def _reject_reparse_components(path: Path) -> None:
    import os

    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        try:
            stat = current.lstat()
        except FileNotFoundError:
            continue
        is_reparse = bool(getattr(stat, "st_file_attributes", 0) & 0x400)
        is_junction = getattr(os.path, "isjunction", lambda _: False)(current)
        if current.is_symlink() or is_reparse or is_junction:
            raise TpexRowBindingError("reparse_path_component_rejected")


if __name__ == "__main__":
    raise SystemExit(main())
