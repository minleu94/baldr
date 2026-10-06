"""WP5 官方日行情 capture 的唯讀 readback validator。

此模組只核對一組已固定 hash 的 QA capture。它不寫 receipt、不接觸資料庫、
不載入 TWStockConfig，也不授予正式 PIT 或臨時休市 negative coverage。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, NoReturn
from zoneinfo import ZoneInfo


OUTPUT_SCHEMA = "wp5-official-daily-capture-readback.v1"
CAPTURE_DIRECTORY_NAME = (
    "wp5_official_daily_capture_20260929_20260929T151827Z_ae0845d9"
)
DEFAULT_DECISION_DATE = date(2026, 9, 29)
REPARSE_POINT_ATTRIBUTE = 0x400
MAX_METADATA_BYTES = 1_000_000
MAX_RAW_BYTES = 64_000_000
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
SYMBOL_RE = re.compile(r"^[A-Za-z0-9]{1,12}$")
INTEGER_RE = re.compile(r"^(?:\d+|\d{1,3}(?:,\d{3})+)$")
UTC_TIMESTAMP_RE = re.compile(
    r"^(?P<base>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<fraction>\d{1,9}))?(?P<zone>Z|\+00:00)$"
)
JSON_CONTENT_TYPE_RE = re.compile(
    r"^\s*application/json\s*(?:;\s*charset\s*=\s*"
    r"(?:[A-Za-z0-9!#$%&'*+.^_`|~-]+|"
    r"\"[A-Za-z0-9!#$%&'*+.^_`|~-]+\")\s*)?$",
    re.IGNORECASE,
)
TAIPEI = ZoneInfo("Asia/Taipei")

TWSE_FIELDS = (
    "證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額", "開盤價",
    "最高價", "最低價", "收盤價", "漲跌(+/-)", "漲跌價差", "最後揭示買價",
    "最後揭示買量", "最後揭示賣價", "最後揭示賣量", "本益比",
)
TPEX_FIELDS = (
    "代號", "名稱", "收盤", "漲跌", "開盤", "最高", "最低", "均價",
    "成交股數", "成交金額(元)", "成交筆數", "最後買價", "最後買量(張數)",
    "最後賣價", "最後賣量(張數)", "發行股數", "次日 參考價", "次日 漲停價",
    "次日 跌停價",
)

def _market_specs(
    decision_date: date,
    required_symbols_by_venue: Mapping[str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    date_compact = decision_date.strftime("%Y%m%d")
    date_slash = (
        f"{decision_date.year:04d}%2F{decision_date.month:02d}"
        f"%2F{decision_date.day:02d}"
    )
    required_twse = required_symbols_by_venue.get("TWSE")
    required_tpex = required_symbols_by_venue.get("TPEx")
    if not isinstance(required_twse, str) or not SYMBOL_RE.fullmatch(required_twse):
        _fail("required_twse_symbol_invalid", "必須提供有效 TWSE 必要代碼。")
    if not isinstance(required_tpex, str) or not SYMBOL_RE.fullmatch(required_tpex):
        _fail("required_tpex_symbol_invalid", "必須提供有效 TPEx 必要代碼。")
    return (
        {
            "name": "twse_mi_index",
            "venue": "TWSE",
            "url": (
                "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
                f"?date={date_compact}&type=ALL&response=json"
            ),
            "filename": f"twse_mi_index_{date_compact}.json",
            "required_symbol": required_twse,
            "fields": TWSE_FIELDS,
            "code_index": 0,
            "shares_index": 2,
            "close_index": 8,
        },
        {
            "name": "tpex_daily_quotes",
            "venue": "TPEx",
            "url": (
                "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes"
                f"?date={date_slash}&id=&response=json"
            ),
            "filename": f"tpex_daily_quotes_{date_compact}.json",
            "required_symbol": required_tpex,
            "fields": TPEX_FIELDS,
            "code_index": 0,
            "shares_index": 8,
            "close_index": 2,
        },
    )


class CaptureValidationError(ValueError):
    """帶穩定機器代碼的唯讀驗證失敗。"""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str) -> NoReturn:
    raise CaptureValidationError(code, detail)


def _normalise_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value.strip()):
        _fail(f"{label}_invalid", "必須提供 64 位十六進位 SHA-256。")
    return value.strip().lower()


def _utc_pair(value: object, label: str) -> tuple[datetime, int]:
    if not isinstance(value, str):
        _fail(f"{label}_invalid", "時間戳必須是含 UTC 時區的 ISO-8601 字串。")
    match = UTC_TIMESTAMP_RE.fullmatch(value)
    if match is None:
        _fail(f"{label}_invalid", "時間戳必須明確使用 Z 或 +00:00，精度最多 9 位。")
    try:
        whole_second = datetime.strptime(
            match.group("base"), "%Y-%m-%dT%H:%M:%S"
        ).replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise CaptureValidationError(
            f"{label}_invalid", "時間戳日期或時間無效。"
        ) from error
    fraction = match.group("fraction") or ""
    nanoseconds = int(fraction.ljust(9, "0")) if fraction else 0
    return whole_second, nanoseconds


def _datetime_pair(value: datetime, label: str) -> tuple[datetime, int]:
    if value.tzinfo is None or value.utcoffset() is None:
        _fail(f"{label}_timezone_missing", "時間必須含時區。")
    utc_value = value.astimezone(timezone.utc)
    whole_second = utc_value.replace(microsecond=0)
    return whole_second, utc_value.microsecond * 1000


def _is_reparse_point(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError as error:
        _fail("path_component_unreadable", f"無法檢查路徑元件：{path} ({error})")
    return stat.S_ISLNK(info.st_mode) or bool(
        int(getattr(info, "st_file_attributes", 0)) & REPARSE_POINT_ATTRIBUTE
    )


def _assert_no_reparse_chain(path: Path) -> None:
    absolute = Path(os.path.abspath(path))
    chain: list[Path] = []
    cursor = absolute
    while True:
        chain.append(cursor)
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    for component in reversed(chain):
        if _is_reparse_point(component):
            _fail("path_reparse_component", f"路徑含 symlink/junction/reparse：{component}")


def _contains(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _resolve_capture_directory(
    capture_directory: str | Path,
    *,
    repo_root: str | Path,
) -> tuple[Path, Path]:
    root_arg = Path(repo_root)
    root_absolute = Path(os.path.abspath(root_arg))
    _assert_no_reparse_chain(root_absolute)
    try:
        root = root_absolute.resolve(strict=True)
    except OSError as error:
        raise CaptureValidationError("repo_root_unavailable", str(root_arg)) from error
    candidate_arg = Path(capture_directory).expanduser()
    if ".." in candidate_arg.parts:
        _fail("capture_path_parent_traversal", "capture path 不可包含 ..。")
    if not candidate_arg.is_absolute():
        candidate_arg = root / candidate_arg
    candidate_absolute = Path(os.path.abspath(candidate_arg))
    _assert_no_reparse_chain(candidate_absolute)
    qa_root_absolute = root / "output" / "qa"
    if not _contains(qa_root_absolute, candidate_absolute):
        _fail("capture_outside_qa_root", "capture 必須位於 repo output/qa 子樹。")
    try:
        candidate = candidate_absolute.resolve(strict=True)
        qa_root = qa_root_absolute.resolve(strict=True)
    except OSError as error:
        raise CaptureValidationError(
            "capture_path_missing", "repo root、output/qa 或 capture 目錄不存在。"
        ) from error
    _assert_no_reparse_chain(qa_root)
    if os.path.normcase(str(candidate)) != os.path.normcase(str(candidate_absolute)):
        _fail("capture_path_resolution_changed", "capture path resolve 後與輸入路徑不同。")
    if not _contains(qa_root, candidate):
        _fail("capture_outside_qa_root", "capture 必須位於 repo output/qa 子樹。")
    if candidate.parent != qa_root:
        _fail("capture_not_direct_qa_child", "capture 必須是 output/qa 的直接子目錄。")
    if not candidate.is_dir():
        _fail("capture_not_directory", "capture path 不是目錄。")
    return root, candidate


def _identity_from_stat(info: os.stat_result, label: str) -> tuple[int, int, int, int, int]:
    device = getattr(info, "st_dev", None)
    inode = getattr(info, "st_ino", None)
    links = getattr(info, "st_nlink", None)
    size = getattr(info, "st_size", None)
    modified = getattr(info, "st_mtime_ns", None)
    if (
        type(device) is not int or device < 0
        or type(inode) is not int or inode <= 0
        or type(links) is not int or links <= 0
        or type(size) is not int or size < 0
        or type(modified) is not int
    ):
        _fail(f"{label}_file_identity_invalid", "缺少可核對的檔案 identity 欄位。")
    if links != 1:
        _fail(f"{label}_hardlink_rejected", f"{label} st_nlink 必須為 1，觀察到 {links}。")
    return device, inode, links, size, modified


def _read_regular_single_link_file(path: Path, *, label: str, max_bytes: int) -> bytes:
    _assert_no_reparse_chain(path)
    try:
        before = path.lstat()
    except OSError as error:
        raise CaptureValidationError(f"{label}_unreadable", str(path)) from error
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        _fail(f"{label}_not_regular_file", f"{label} 必須是普通檔案。")
    before_identity = _identity_from_stat(before, label)
    if before_identity[3] > max_bytes:
        _fail(f"{label}_size_limit", f"{label} 超過唯讀驗證大小上限。")
    try:
        with path.open("rb") as stream:
            opened_identity = _identity_from_stat(os.fstat(stream.fileno()), label)
            if opened_identity != before_identity:
                _fail(f"{label}_identity_changed", f"{label} 開啟時 identity 已改變。")
            chunks: list[bytes] = []
            total = 0
            while True:
                block = stream.read(min(1024 * 1024, max_bytes + 1 - total))
                if not block:
                    break
                chunks.append(block)
                total += len(block)
                if total > max_bytes:
                    _fail(f"{label}_size_limit", f"{label} 讀取期間超過大小上限。")
            after_open_identity = _identity_from_stat(os.fstat(stream.fileno()), label)
        after = path.lstat()
    except CaptureValidationError:
        raise
    except OSError as error:
        raise CaptureValidationError(f"{label}_unreadable", str(path)) from error
    after_identity = _identity_from_stat(after, label)
    if not (before_identity == opened_identity == after_open_identity == after_identity):
        _fail(f"{label}_identity_changed", f"{label} 讀取期間 identity 有變化。")
    if total != before_identity[3]:
        _fail(f"{label}_length_changed", f"{label} 實際讀取長度與 stat 不符。")
    return b"".join(chunks)


def _read_json_file(path: Path, *, label: str, expected_sha256: str | None = None) -> tuple[dict[str, Any], str]:
    raw = _read_regular_single_link_file(
        path, label=label, max_bytes=MAX_METADATA_BYTES
    )
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        _fail(f"{label}_sha256_mismatch", f"{label} 與 caller pin 不符。")
    try:
        value = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CaptureValidationError(f"{label}_invalid_json", "JSON 無法解碼。") from error
    if not isinstance(value, dict):
        _fail(f"{label}_not_object", "JSON 根節點必須是 object。")
    return value, digest


def _reject_untrusted_publication_claims(value: object) -> None:
    """Do not accept caller-captured metadata as an official publication time."""

    publication_keys = {
        "official_published_at",
        "official_published_at_utc",
        "published_at",
        "published_at_utc",
        "publication_at",
        "publication_at_utc",
    }
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str) and key.casefold() in publication_keys:
                if item is not None and not (
                    isinstance(item, str) and item.strip().casefold() == "unknown"
                ):
                    _fail(
                        "capture_publication_time_claim_rejected",
                        "capture metadata 不得宣稱未經獨立驗證的 official published_at。",
                    )
            _reject_untrusted_publication_claims(item)
    elif isinstance(value, list):
        for item in value:
            _reject_untrusted_publication_claims(item)


def _timestamp_text(value: object, label: str) -> tuple[str, tuple[datetime, int]]:
    if not isinstance(value, str):
        _fail(f"{label}_invalid", "缺少 UTC 時間戳。")
    return value, _utc_pair(value, label)


def _parse_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        _fail(f"{label}_invalid", "成交股數必須是非負整數文字。")
    text = str(value).strip()
    if not INTEGER_RE.fullmatch(text):
        _fail(f"{label}_invalid", f"成交股數格式不合法：{text!r}")
    return int(text.replace(",", ""))


def _positive_close(value: object, label: str) -> str:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        _fail(f"{label}_invalid", "必要代碼收盤價格式不合法。")
    text = str(value).strip().replace(",", "")
    try:
        close = Decimal(text)
    except InvalidOperation as error:
        raise CaptureValidationError(f"{label}_invalid", "必要代碼收盤價不是數值。") from error
    if not close.is_finite() or close <= 0:
        _fail(f"{label}_not_positive", "必要代碼收盤價必須是有限正數。")
    return str(close)


def _decode_json_body(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CaptureValidationError(f"{label}_invalid_json", "raw response 不是完整 UTF-8 JSON。") from error
    if not isinstance(value, dict):
        _fail(f"{label}_root_not_object", "raw response JSON 根節點必須是 object。")
    return value


def _validate_market_rows(
    *,
    market: dict[str, Any],
    rows: object,
) -> dict[str, Any]:
    name = str(market["name"])
    if not isinstance(rows, list) or not rows:
        _fail(f"{name}_empty_rows", "全市場每日行情資料列不可為空。")
    code_index = int(market["code_index"])
    shares_index = int(market["shares_index"])
    close_index = int(market["close_index"])
    field_count = len(market["fields"])
    seen: set[str] = set()
    shares_by_code: dict[str, int] = {}
    close_by_code: dict[str, str] = {}
    positive_volume_rows = 0
    for row_number, row in enumerate(rows, start=1):
        if not isinstance(row, list) or len(row) != field_count:
            _fail(
                f"{name}_row_shape_invalid",
                f"第 {row_number} 列欄位數不符合官方 schema。",
            )
        raw_code = row[code_index]
        if not isinstance(raw_code, (str, int)) or isinstance(raw_code, bool):
            _fail(f"{name}_symbol_invalid", f"第 {row_number} 列代碼型別不合法。")
        code = str(raw_code).strip()
        if not SYMBOL_RE.fullmatch(code):
            _fail(f"{name}_symbol_invalid", f"第 {row_number} 列證券代碼格式不合法。")
        if code in seen:
            _fail(f"{name}_duplicate_symbol", f"官方資料有重複證券代碼：{code}。")
        seen.add(code)
        shares = _parse_integer(row[shares_index], f"{name}_shares_row_{row_number}")
        if shares > 0:
            positive_volume_rows += 1
        shares_by_code[code] = shares
        if code == market["required_symbol"]:
            close_by_code[code] = _positive_close(
                row[close_index], f"{name}_required_close_{code}"
            )

    required_symbol = str(market["required_symbol"])
    if required_symbol not in seen:
        _fail(f"{name}_required_symbol_missing", f"缺少必要代碼 {required_symbol}。")
    required_shares = shares_by_code[required_symbol]
    if required_shares <= 0:
        _fail(
            f"{name}_required_symbol_no_positive_volume",
            f"必要代碼 {required_symbol} 成交股數必須為正。",
        )
    return {
        "venue": market["venue"],
        "rows": len(rows),
        "unique_codes": len(seen),
        "positive_volume_rows": positive_volume_rows,
        "required_symbol": required_symbol,
        "required_symbol_volume_shares": required_shares,
        "required_symbol_close": close_by_code[required_symbol],
    }


def _validate_twse(raw: bytes, *, market: dict[str, Any], decision_date: date) -> dict[str, Any]:
    payload = _decode_json_body(raw, "twse_mi_index")
    if payload.get("date") != decision_date.strftime("%Y%m%d"):
        _fail("twse_date_mismatch", "TWSE 回應 date 與 caller decision_date 不符。")
    if payload.get("stat") != "OK":
        _fail("twse_stat_not_ok", "TWSE 回應 stat 不是 OK。")
    if payload.get("type") != "ALL":
        _fail("twse_type_not_all", "TWSE 回應 type 不是 ALL。")
    tables = payload.get("tables")
    if not isinstance(tables, list) or len(tables) <= 8:
        _fail("twse_daily_table_missing", "TWSE tables[8] 每日收盤行情表缺失。")
    table = tables[8]
    if not isinstance(table, dict) or tuple(table.get("fields", ())) != TWSE_FIELDS:
        _fail("twse_daily_fields_mismatch", "TWSE tables[8] 欄位不符合每日收盤行情契約。")
    result = _validate_market_rows(market=market, rows=table.get("data"))
    result["table_index"] = 8
    return result


def _validate_tpex(raw: bytes, *, market: dict[str, Any], decision_date: date) -> dict[str, Any]:
    payload = _decode_json_body(raw, "tpex_daily_quotes")
    if payload.get("date") != decision_date.strftime("%Y%m%d"):
        _fail("tpex_date_mismatch", "TPEx 回應 date 與 caller decision_date 不符。")
    if payload.get("stat") != "ok":
        _fail("tpex_stat_not_ok", "TPEx 回應 stat 不是 ok。")
    tables = payload.get("tables")
    if not isinstance(tables, list) or not tables:
        _fail("tpex_daily_table_missing", "TPEx tables[0] 每日行情表缺失。")
    table = tables[0]
    if not isinstance(table, dict) or tuple(table.get("fields", ())) != TPEX_FIELDS:
        _fail("tpex_daily_fields_mismatch", "TPEx tables[0] 欄位不符合 dailyQuotes 契約。")
    rows = table.get("data")
    if not isinstance(rows, list):
        _fail("tpex_daily_rows_invalid", "TPEx tables[0].data 必須是資料列清單。")
    result = _validate_market_rows(market=market, rows=rows)
    total_count = table.get("totalCount")
    if type(total_count) is not int or total_count != len(rows):
        _fail("tpex_total_count_mismatch", "TPEx tables[0].totalCount 必須等於資料列數。")
    result["table_index"] = 0
    result["total_count"] = total_count
    return result


def validate_official_daily_capture(
    capture_directory: str | Path,
    *,
    expected_receipt_sha256: str,
    expected_manifest_sha256: str,
    decision_date: date,
    required_symbols_by_venue: Mapping[str, str],
    cutoff_utc: datetime,
    repo_root: str | Path,
) -> dict[str, Any]:
    """唯讀驗證 caller 固定日期的 TWSE/TPEx raw capture 並回傳有限 evidence。"""

    if not isinstance(decision_date, date) or isinstance(decision_date, datetime):
        _fail("decision_date_invalid", "decision_date 必須是 datetime.date。")
    markets = _market_specs(decision_date, required_symbols_by_venue)
    receipt_pin = _normalise_sha256(expected_receipt_sha256, "expected_receipt_sha256")
    manifest_pin = _normalise_sha256(expected_manifest_sha256, "expected_manifest_sha256")
    cutoff_pair = _datetime_pair(cutoff_utc, "cutoff_utc")
    now_pair = _datetime_pair(datetime.now(timezone.utc), "now_utc")
    if cutoff_pair > now_pair:
        _fail("cutoff_in_future", "caller cutoff 不可晚於驗證時鐘。")
    if cutoff_utc.astimezone(TAIPEI).date() < decision_date:
        _fail("cutoff_before_decision_date", "cutoff 台北日期不可早於 decision_date。")

    _, capture_dir = _resolve_capture_directory(
        capture_directory, repo_root=repo_root
    )
    receipt_path = capture_dir / "capture_receipt.json"
    manifest_path = capture_dir / "capture_manifest.json"
    receipt, receipt_sha = _read_json_file(
        receipt_path, label="receipt", expected_sha256=receipt_pin
    )
    manifest, manifest_sha = _read_json_file(
        manifest_path, label="manifest", expected_sha256=manifest_pin
    )
    _reject_untrusted_publication_claims(receipt)
    _reject_untrusted_publication_claims(manifest)
    run_id = receipt.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip() or manifest.get("run_id") != run_id:
        _fail("capture_run_id_mismatch", "receipt/manifest 必須有相同且非空的 run_id。")
    for label, value in (("receipt", receipt), ("manifest", manifest)):
        if type(value.get("schema_version")) is not int or value["schema_version"] != 1:
            _fail(f"{label}_schema_version_unsupported", "capture metadata schema_version 必須為 1。")
        if value.get("run_status") != "success_raw_capture_readback_verified":
            _fail(f"{label}_run_status_not_verified", "capture metadata 未標記 raw readback verified。")
        if not _same_absolute_path(value.get("capture_directory"), capture_dir):
            _fail(f"{label}_capture_directory_mismatch", "metadata capture_directory 與輸入路徑不符。")
    if receipt.get("formal_pit") is not False:
        _fail("receipt_formal_pit_must_be_false", "capture receipt 必須明示 formal_pit=false。")
    if manifest.get("receipt_file") != "capture_receipt.json":
        _fail("manifest_receipt_file_mismatch", "manifest receipt_file 名稱不符。")

    started_text, started = _timestamp_text(receipt.get("started_at_utc"), "started_at_utc")
    finished_text, finished = _timestamp_text(receipt.get("finished_at_utc"), "finished_at_utc")
    if started >= finished:
        _fail("capture_run_chronology_invalid", "capture run 起訖時間順序錯誤。")

    captures = receipt.get("captures")
    raw_files = manifest.get("raw_files")
    if not isinstance(captures, list) or len(captures) != 2:
        _fail("receipt_capture_set_incomplete", "receipt 必須包含且僅包含兩個市場 capture。")
    if not isinstance(raw_files, list) or len(raw_files) != 2:
        _fail("manifest_raw_file_set_incomplete", "manifest 必須包含且僅包含兩個市場 raw file。")

    results: dict[str, dict[str, Any]] = {}
    capture_intervals: list[tuple[tuple[datetime, int], tuple[datetime, int]]] = []
    capture_ends: list[tuple[tuple[datetime, int], str]] = []
    for market, capture, manifest_entry in zip(markets, captures, raw_files, strict=True):
        name = str(market["name"])
        if not isinstance(capture, dict) or not isinstance(manifest_entry, dict):
            _fail("capture_entry_invalid", "receipt/manifest 市場項目必須是 JSON object。")
        if capture.get("name") != name or manifest_entry.get("name") != name:
            _fail("capture_market_order_or_name_mismatch", "市場 capture 順序或名稱不符。")
        if capture.get("request_url") != market["url"] or capture.get("final_url") != market["url"]:
            _fail(f"{name}_official_url_mismatch", "request/final URL 必須精確符合官方 endpoint pin。")
        if type(capture.get("http_status")) is not int or capture["http_status"] != 200:
            _fail(f"{name}_http_status_not_200", "官方 response HTTP status 必須為 200。")
        content_type = capture.get("content_type")
        if (
            not isinstance(content_type, str)
            or JSON_CONTENT_TYPE_RE.fullmatch(content_type) is None
        ):
            _fail(
                f"{name}_content_type_invalid",
                "官方 response media type 必須精確為 application/json，參數限合法 charset。",
            )
        if capture.get("body_file") != market["filename"]:
            _fail(f"{name}_filename_mismatch", "receipt body_file 不符合固定檔名。")
        start_text, start = _timestamp_text(capture.get("capture_start_utc"), f"{name}_capture_start")
        end_text, end = _timestamp_text(capture.get("capture_end_utc"), f"{name}_capture_end")
        if start >= end:
            _fail(f"{name}_capture_chronology_invalid", "單一市場 capture start 必須早於 end。")
        if start < started or end > finished:
            _fail(f"{name}_outside_run_chronology", "市場 capture 時間超出 receipt run 起訖。")
        if end > cutoff_pair:
            _fail(f"{name}_after_cutoff", "市場 response body 完成時間晚於 caller cutoff。")
        if start[0].astimezone(TAIPEI).date() != decision_date:
            _fail(f"{name}_capture_date_mismatch", "capture start 台北日期必須等於 caller decision_date。")
        if end[0].astimezone(TAIPEI).date() != decision_date:
            _fail(f"{name}_capture_date_mismatch", "capture end 台北日期必須等於 caller decision_date。")
        capture_intervals.append((start, end))
        capture_ends.append((end, end_text))

        body_sha = _normalise_sha256(capture.get("body_sha256"), f"{name}_receipt_sha256")
        try:
            body_bytes = capture.get("body_bytes")
            readback_bytes = capture.get("readback_bytes")
            if type(body_bytes) is not int or type(readback_bytes) is not int:
                raise TypeError
            readback_sha = _normalise_sha256(capture.get("readback_sha256"), f"{name}_readback_sha256")
        except (TypeError, CaptureValidationError) as error:
            if isinstance(error, CaptureValidationError):
                raise
            _fail(f"{name}_length_invalid", "receipt body/readback byte length 必須是整數。")
        if body_bytes <= 0 or readback_bytes != body_bytes or readback_sha != body_sha:
            _fail(f"{name}_receipt_readback_mismatch", "receipt 內 body/readback size 或 hash 不一致。")
        if capture.get("readback_verified") is not True or capture.get("result") != "captured_verified":
            _fail(f"{name}_receipt_readback_unverified", "receipt 未標示 readback verified。")

        expected_manifest_entry = {
            "name": name,
            "file": market["filename"],
            "http_status": 200,
            "bytes": body_bytes,
            "sha256": body_sha,
            "readback_bytes": body_bytes,
            "readback_sha256": body_sha,
            "readback_verified": True,
        }
        for key, expected in expected_manifest_entry.items():
            actual = manifest_entry.get(key)
            if actual != expected or (key == "readback_verified" and actual is not True):
                _fail(f"{name}_manifest_entry_mismatch", f"manifest 欄位 {key} 與 receipt 不一致。")

        body_path = capture_dir / market["filename"]
        raw = _read_regular_single_link_file(
            body_path, label=f"{name}_raw", max_bytes=MAX_RAW_BYTES
        )
        actual_sha = hashlib.sha256(raw).hexdigest()
        if len(raw) != body_bytes or actual_sha != body_sha:
            _fail(f"{name}_raw_readback_mismatch", "raw bytes 長度或 SHA-256 與固定 receipt 不符。")
        if name == "twse_mi_index":
            market_result = _validate_twse(
                raw, market=market, decision_date=decision_date
            )
        else:
            market_result = _validate_tpex(
                raw, market=market, decision_date=decision_date
            )
        market_result["raw_bytes"] = len(raw)
        market_result["raw_sha256"] = actual_sha
        results[name] = market_result

    if capture_intervals[0][1] > capture_intervals[1][0]:
        _fail("market_capture_order_invalid", "TWSE capture 必須先於 TPEx capture，且不得重疊。")
    latest_end_pair, latest_end_text = max(capture_ends, key=lambda item: item[0])
    if latest_end_pair > _utc_pair(finished_text, "finished_at_utc"):
        _fail("capture_finished_before_body", "receipt finished_at 早於最晚 response body 完成。")

    return {
        "schema_version": OUTPUT_SCHEMA,
        "status": "validated",
        "evidence_kind": "official_same_day_market_activity_observed",
        "evidence_scope": "same_day_market_activity_only",
        "decision_date": decision_date.isoformat(),
        "capture_run_id": run_id,
        "capture_directory": str(capture_dir),
        "cutoff_utc": _format_datetime_utc(cutoff_utc),
        "receipt_sha256": receipt_sha,
        "manifest_sha256": manifest_sha,
        "markets": results,
        "available_at_utc": latest_end_text,
        "availability_basis": "max_capture_end_utc_local_body_read_complete",
        "official_published_at_utc": "unknown",
        "temporary_closure_negative_coverage": False,
        "closure_gate_passed": False,
        "formal_pit": False,
        "notes": [
            "此結果只表示兩個官方全市場回應均含同日正向交易資料列。",
            "capture_end_utc 是保守的本地讀取完成時間，不是官方發布時間。",
            "此結果不等於完整臨時休市 negative coverage，也不構成正式 PIT。",
        ],
    }


def _format_datetime_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="auto").replace(
        "+00:00", "Z"
    )


def _same_absolute_path(value: object, expected: Path) -> bool:
    if not isinstance(value, str) or not value:
        return False
    candidate = Path(value)
    if not candidate.is_absolute() or ".." in candidate.parts:
        return False
    return os.path.normcase(os.path.abspath(candidate)) == os.path.normcase(str(expected))


def blocked_result(error: CaptureValidationError) -> dict[str, Any]:
    """將驗證失敗轉為穩定 stdout JSON payload。"""

    return {
        "schema_version": OUTPUT_SCHEMA,
        "status": "blocked",
        "evidence_kind": "official_same_day_market_activity_observed",
        "evidence_scope": "same_day_market_activity_only",
        "temporary_closure_negative_coverage": False,
        "closure_gate_passed": False,
        "formal_pit": False,
        "blockers": [{"code": error.code, "detail": error.detail}],
    }
