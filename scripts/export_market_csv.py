"""Windows 市場 CSV 隔離 CLI；預設唯讀 preview，執行需明示接受來源 pins。"""

from __future__ import annotations

import argparse
import json
import os
from contextlib import ExitStack
from pathlib import Path
import signal
import sys
from typing import Callable, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.market_csv_export import (
    RECEIPT_NAME,
    MarketCsvExportCancelled,
    MarketCsvExportError,
    _DirectoryPins,
    _PRIVATE_PARTS,
    _check_cancel,
    _hash_file,
    _identity,
    _open_file,
    export_market_csv,
)
from app_module.personal_data_paths import (
    MarketOnlyExportPlan,
    PersonalDataPathError,
    _absolute,
    _file_identity,
    plan_market_only_export,
    resolve_personal_data_paths,
)

PREVIEW_SCHEMA = "market-csv-export-preview.v1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(
        "僅支援 Windows handle sharing；預設 preview 不寫。只接受明列市場 CSV，"
        "排除 personal／output／SQLite，禁止整包 FA_Data；不做上傳或分享。"))
    parser.add_argument("--market-root", type=Path, required=True, help="明示 absolute 市場來源 root")
    parser.add_argument("--destination-root", type=Path, required=True, help="隔離全新目標；父目錄已存在，不可覆寫")
    parser.add_argument("--file", action="append", required=True, dest="relative_files",
                        help="明列 whitelist 相對 CSV，可重複選項；不接受 glob／整包／SQLite")
    parser.add_argument("--personal-root", type=Path, help="未指定時只使用 market-root/personal；不建立")
    parser.add_argument("--legacy-output-root", type=Path, help="未指定時 market-root/output；同樣排除")
    parser.add_argument("--execute", action="store_true", help="明示執行 copy；需 --accepted-preview")
    parser.add_argument("--accepted-preview", type=Path, help="caller 已核對的 preview JSON；來源 identity/hash 不得變")
    return parser


def _validate_target_and_names(plan: MarketOnlyExportPlan) -> None:
    if not plan.files:
        raise MarketCsvExportError("empty_market_export_plan")
    if plan.destination_root.exists():
        raise MarketCsvExportError("export_destination_exists", plan.destination_root)
    if not plan.destination_root.parent.is_dir():
        raise MarketCsvExportError("export_parent_missing", plan.destination_root.parent)
    for entry in plan.files:
        parts = Path(entry.relative_path).parts
        if any(part.casefold() in _PRIVATE_PARTS for part in parts):
            raise MarketCsvExportError("private_export_component", entry.relative_path)
        if any(token in parts[-1].casefold() for token in (".sqlite", ".db", "-wal", "-shm", "-journal")):
            raise MarketCsvExportError("sqlite_name_excluded", entry.relative_path)


def _observe(plan: MarketOnlyExportPlan, cancelled: Callable[[], bool]) -> list[dict[str, object]]:
    observed: list[dict[str, object]] = []
    with ExitStack() as stack:
        pins = _DirectoryPins(stack)
        for entry in plan.files:
            _check_cancel(cancelled)
            pins.pin(entry.source_path.parent)
            stream = stack.enter_context(_open_file(entry.source_path))
            if _identity(os.fstat(stream.fileno())) != entry.identity:
                raise MarketCsvExportError("export_source_identity_changed", entry.source_path)
            digest = _hash_file(stream, cancelled)
            if _file_identity(entry.source_path) != entry.identity:
                raise MarketCsvExportError("export_source_identity_changed", entry.source_path)
            observed.append({"relative_path": entry.relative_path, "source_identity": list(entry.identity),
                             "size_bytes": entry.identity[2], "sha256": digest})
        plan.validate()
        pins.validate()
    return observed


def _accepted_hashes(path: Path, plan: MarketOnlyExportPlan) -> dict[str, str]:
    # 只讀 caller 明示的新 preview 文件；不接受 link、hardlink 或私人來源路徑。
    value = _absolute(path)
    if any(value.is_relative_to(root) for root in (plan.paths.market_root, plan.paths.personal_root,
                                                  plan.paths.legacy_output_root, plan.destination_root)):
        raise MarketCsvExportError("accepted_preview_must_be_isolated", value)
    with ExitStack() as stack:
        pins = _DirectoryPins(stack)
        pins.pin(value.parent)
        expected_identity = _file_identity(value)
        stream = stack.enter_context(_open_file(value))
        if _identity(os.fstat(stream.fileno())) != expected_identity or expected_identity[2] > 1024 * 1024:
            raise MarketCsvExportError("accepted_preview_invalid", value)
        raw = stream.read(1024 * 1024 + 1)
        if _file_identity(value) != expected_identity:
            raise MarketCsvExportError("accepted_preview_changed", value)
        pins.validate()
    document = json.loads(raw)
    if not isinstance(document, dict) or document.get("schema") != PREVIEW_SCHEMA or document.get("status") != "preview":
        raise MarketCsvExportError("accepted_preview_invalid", value)
    roots = {"market_root": str(plan.paths.market_root), "personal_root": str(plan.paths.personal_root),
             "legacy_output_root": str(plan.paths.legacy_output_root)}
    if document.get("source_roots") != roots:
        raise MarketCsvExportError("accepted_preview_roots_changed", value)
    entries = document.get("observed_source_pins")
    if not isinstance(entries, list) or len(entries) != len(plan.files):
        raise MarketCsvExportError("accepted_preview_files_changed", value)
    by_name = {entry.relative_path: entry for entry in plan.files}
    hashes: dict[str, str] = {}
    for pin in entries:
        if not isinstance(pin, dict) or not isinstance(pin.get("relative_path"), str):
            raise MarketCsvExportError("accepted_preview_invalid", value)
        name = pin["relative_path"]
        entry = by_name.get(name)
        identity = pin.get("source_identity")
        digest = pin.get("sha256")
        if entry is None or name in hashes:
            raise MarketCsvExportError("accepted_preview_files_changed", name)
        if not isinstance(identity, list) or any(type(item) is not int for item in identity) or tuple(identity) != entry.identity:
            raise MarketCsvExportError("accepted_preview_source_changed", name)
        if type(pin.get("size_bytes")) is not int or pin["size_bytes"] != entry.identity[2]:
            raise MarketCsvExportError("accepted_preview_source_changed", name)
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise MarketCsvExportError("accepted_preview_invalid_hash", name)
        hashes[name] = digest
    return hashes


def main(argv: Sequence[str] | None = None, *, cancelled: Callable[[], bool] | None = None) -> int:
    args = build_parser().parse_args(argv)
    interrupted = False

    def stop(signum: int, frame: object) -> None:
        nonlocal interrupted
        interrupted = True

    def is_cancelled() -> bool:
        return interrupted or (cancelled is not None and cancelled())

    previous_handler = signal.signal(signal.SIGINT, stop)
    code = 0
    try:
        if os.name != "nt":
            raise MarketCsvExportError("export_platform_unsupported")
        if args.execute and args.accepted_preview is None:
            raise MarketCsvExportError("execute_requires_accepted_preview")
        if not args.execute and args.accepted_preview is not None:
            raise MarketCsvExportError("accepted_preview_requires_execute")
        _check_cancel(is_cancelled)
        paths = resolve_personal_data_paths(args.market_root,
            personal_root=args.personal_root if args.personal_root is not None else args.market_root / "personal",
            legacy_output_root=args.legacy_output_root, environ={})
        plan = plan_market_only_export(paths, args.relative_files, destination_root=args.destination_root)
        _validate_target_and_names(plan)
        if args.execute:
            hashes = _accepted_hashes(args.accepted_preview, plan)
            receipt = export_market_csv(plan, expected_sha256=hashes, cancelled=is_cancelled)
            result: dict[str, object] = {"schema": "market-csv-export-cli.v1", "status": "completed",
                "destination_root": str(receipt.destination_root), "receipt_path": str(receipt.receipt_path),
                "receipt_sha256": receipt.receipt_sha256, "file_count": len(receipt.files),
                "total_size_bytes": sum(entry.size_bytes for entry in receipt.files), "uploaded": False, "shared": False}
        else:
            observed = _observe(plan, is_cancelled)
            result = {"schema": PREVIEW_SCHEMA, "status": "preview", "platform": "Windows handle sharing required",
                "source_roots": {"market_root": str(paths.market_root), "personal_root": str(paths.personal_root),
                                 "legacy_output_root": str(paths.legacy_output_root)},
                "destination_root": str(plan.destination_root), "observed_source_pins": observed,
                "file_count": len(plan.files), "total_size_bytes": sum(entry.identity[2] for entry in plan.files),
                "excluded": ["personal subtree", "legacy output", "SQLite/DB/sidecars", "unlisted files"],
                "completion_receipt": RECEIPT_NAME, "source_hashes_accepted": False,
                "writes_performed": False, "uploaded": False, "shared": False,
                "execute_requires": "--execute --accepted-preview <caller-reviewed-preview.json>",
                "retry_rule": "取消或失敗保留 partial／pending；重試必須明示另一全新目標。"}
    except (MarketCsvExportCancelled, KeyboardInterrupt):
        result = {"schema": "market-csv-export-cli.v1", "status": "cancelled", "code": "export_cancelled",
                  "destination_root": str(args.destination_root), "completion_published": False,
                  "retry_rule": "保留 partial／pending；重試必須指定另一全新目標。"}
        code = 130
    except (PersonalDataPathError, OSError, ValueError) as exc:
        result = {"schema": "market-csv-export-cli.v1", "status": "blocked",
                  "code": str(getattr(exc, "code", type(exc).__name__)), "error_type": type(exc).__name__,
                  "destination_root": str(args.destination_root), "completion_published": False,
                  "retry_rule": "既有目標不覆寫；partial／pending 保留，使用另一全新目標。"}
        code = 2
    finally:
        signal.signal(signal.SIGINT, previous_handler)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return code


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
