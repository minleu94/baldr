"""以明確 request 執行個人模型日常生成與隔離自然結果發布。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, NoReturn, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MAX_REQUEST_BYTES = 1024 * 1024
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_REPARSE_POINT = 0x400
_SUCCESS_STATUSES = {"completed", "completed_with_pending"}
_KNOWN_STATUSES = _SUCCESS_STATUSES | {
    "completed_with_unknown",
    "failed",
    "cancelled",
}


class _RequestError(ValueError):
    """CLI request envelope 不符合本機讀取契約。"""


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        _write_json(
            {
                "status": "failed",
                "error_type": "CLIArgumentError",
                "message": message,
            }
        )
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = _JsonArgumentParser(
        description="依固定 request 與來源 bytes pin 執行個人模型日常工作。"
    )
    parser.add_argument(
        "--request-json",
        required=True,
        help="絕對路徑的 UTF-8 request JSON 檔案，最多 1 MiB。",
    )
    parser.add_argument(
        "--request-sha256",
        required=True,
        help="request 原始 bytes 的 sha256:<64 個小寫十六進位字元>。",
    )
    parser.add_argument(
        "--receipt-root",
        required=True,
        help="絕對路徑的隔離 receipt 根目錄。",
    )
    return parser


def _is_reparse_point(mode: int, attributes: int) -> bool:
    return stat.S_ISLNK(mode) or bool(attributes & _REPARSE_POINT)


def _require_absolute_path(value: str, field: str) -> Path:
    path = Path(value) if value else Path()
    if not value or not path.is_absolute():
        raise _RequestError(f"{field} 必須是絕對路徑")
    if ".." in path.parts:
        raise _RequestError(f"{field} 不可包含父層路徑元件")
    return path


def _identity(info: os.stat_result) -> tuple[int, int]:
    return (int(info.st_dev), int(info.st_ino))


def _read_bounded_plain_request(path: Path) -> bytes:
    """只讀取穩定、一般檔案的有限 bytes，拒絕 symbolic/reparse link。"""

    for parent in reversed(path.parents):
        try:
            parent_info = parent.lstat()
        except OSError as exc:
            raise _RequestError("request-json 的既有父層無法安全讀取") from exc
        parent_attributes = int(getattr(parent_info, "st_file_attributes", 0))
        if (
            not stat.S_ISDIR(parent_info.st_mode)
            or _is_reparse_point(parent_info.st_mode, parent_attributes)
        ):
            raise _RequestError("request-json 父層必須是一般目錄且不可為連結")

    try:
        before = path.lstat()
    except OSError as exc:
        raise _RequestError("request-json 無法讀取") from exc
    before_attributes = int(getattr(before, "st_file_attributes", 0))
    if not stat.S_ISREG(before.st_mode) or _is_reparse_point(
        before.st_mode, before_attributes
    ):
        raise _RequestError("request-json 必須是一般檔案且不可為連結")
    if int(getattr(before, "st_nlink", 1)) != 1:
        raise _RequestError("request-json 不可有多個硬連結")
    if before.st_size > MAX_REQUEST_BYTES:
        raise _RequestError("request-json 超過 1 MiB 上限")

    flags = os.O_RDONLY
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise _RequestError("request-json 無法安全開啟") from exc

    try:
        opened = os.fstat(descriptor)
        opened_attributes = int(getattr(opened, "st_file_attributes", 0))
        if (
            not stat.S_ISREG(opened.st_mode)
            or _is_reparse_point(opened.st_mode, opened_attributes)
            or int(getattr(opened, "st_nlink", 1)) != 1
            or _identity(before) != _identity(opened)
            or before.st_size != opened.st_size
            or before.st_mtime_ns != opened.st_mtime_ns
        ):
            raise _RequestError("request-json 在安全檢查期間發生變更")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            raise _RequestError("request-json 超過 1 MiB 上限")
        if len(raw) != opened.st_size:
            raise _RequestError("request-json 讀取長度與檔案大小不符")
        after = os.fstat(descriptor)
        try:
            final_path = path.lstat()
        except OSError as exc:
            raise _RequestError("request-json 在讀取期間消失") from exc
        if (
            _identity(opened) != _identity(after)
            or _identity(opened) != _identity(final_path)
            or int(getattr(after, "st_nlink", 1)) != 1
            or int(getattr(final_path, "st_nlink", 1)) != 1
            or not stat.S_ISREG(final_path.st_mode)
            or opened.st_size != after.st_size
            or opened.st_mtime_ns != after.st_mtime_ns
            or opened.st_size != final_path.st_size
            or opened.st_mtime_ns != final_path.st_mtime_ns
            or _is_reparse_point(
                final_path.st_mode,
                int(getattr(final_path, "st_file_attributes", 0)),
            )
        ):
            raise _RequestError("request-json 在讀取期間發生變更")
        return raw
    finally:
        os.close(descriptor)


def _decode_request(raw: bytes, expected_sha256: str) -> dict[str, Any]:
    if not _SHA256_RE.fullmatch(expected_sha256):
        raise _RequestError("request-sha256 格式無效")
    actual = "sha256:" + hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256:
        raise _RequestError("request 原始 bytes 與 request-sha256 不符")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _RequestError("request-json 必須是有效 UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise _RequestError("request-json 最外層必須是 JSON object")
    return value


def _load_api_runner():
    # 延後匯入，讓 --help 只解析 CLI 而不載入執行服務。
    from app_module.recommendation.personal_natural_outcome_daily import (
        run_personal_model_daily,
    )

    return run_personal_model_daily


def _write_json(payload: dict[str, Any]) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _failure_payload(exc: BaseException) -> dict[str, Any]:
    message = str(exc).replace("\r", " ").replace("\n", " ")[:500]
    return {
        "status": "failed",
        "error_type": type(exc).__name__,
        "message": message,
    }


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        request_path = _require_absolute_path(args.request_json, "request-json")
        receipt_root = _require_absolute_path(args.receipt_root, "receipt-root")
        raw = _read_bounded_plain_request(request_path)
        request = _decode_request(raw, args.request_sha256)
        receipt = _load_api_runner()(request=request, receipt_root=receipt_root)
        if not isinstance(receipt, dict):
            raise _RequestError("daily API 必須回傳 receipt object")
        status = receipt.get("status")
        if status not in _KNOWN_STATUSES:
            raise _RequestError("daily API 回傳未知 receipt status")
        _write_json(receipt)
        if status == "cancelled":
            return 130
        if status in {"failed", "completed_with_unknown"}:
            return 2
        return 0
    except KeyboardInterrupt as exc:
        _write_json(_failure_payload(exc) | {"status": "cancelled"})
        return 130
    except Exception as exc:
        _write_json(_failure_payload(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
