"""TWSE 單日注意公告的不可覆寫版本與明選 reader；不授交易或歷史 PIT 資格。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app_module.recommendation_portfolio_calendar_artifact_v1 import (
    _canonical_path, _read_exact_file, _reject_constant, _reject_duplicate_keys,
    _reject_float, _validate_json_depth,
)
from app_module.position_health_saved_archive import _create_immutable_bytes
from data_module.daily_source_snapshot import DAILY_SOURCE_TIME_BASIS_POLICY, _batch_publish_guard_hour
from data_module.selection_official_attention import (
    ATTENTION_PARSER_VERSION, MAX_ATTENTION_RAW_BYTES, OfficialAttentionReport,
    OfficialAttentionRow, attention_query_url, parse_official_attention_report,
)

_TAIPEI = ZoneInfo("Asia/Taipei")
_MANIFEST = "twse-attention-daily-manifest.v1"
_RECEIPT = "twse-attention-daily-receipt.v1"
_BASIS = "successful_batch_completion_fallback"
# 此三份實際官方原件只證查詢契約；不是授權或規則權威接受。
ATTENTION_DOCUMENT_PINS = {
    "notice.html": "1a238a5cb47b7846c287af2b33d24aea881e8455aa60bce987dc6201b69ac3cc",
    "web-report.js": "fb42365f6eb8a1516408e7604f502c134c5e54de0c4f6449c6e10c2915685058",
    "main.js": "71199f09be305810c1600804c19a14706064e60304a249ae5c3bd2556de94426",
}
_FILES = ("response.raw", "http-receipt.json", "headers.json", "worker_input.json",
          "worker_result.json", "worker_job.json", "cookies.before_request.json", "cookies.after_headers.json")


class OfficialAttentionSnapshotError(ValueError):
    """來源、版本或可用時鐘不合格時只隔離注意公告。"""


def _hash(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _sha(value: str) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise OfficialAttentionSnapshotError("必須明示小寫SHA256")
    return value


def _local(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(parsed, datetime) or parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OfficialAttentionSnapshotError("批次與決策時鐘必須含時區")
    return parsed.astimezone(_TAIPEI)


def _json(raw: bytes, *, transport: bool = False) -> Any:
    _validate_json_depth(raw)
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_reject_duplicate_keys,
                      parse_constant=_reject_constant, parse_float=Decimal if transport else _reject_float)


def _bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _cancel(callback: Callable[[], bool] | None) -> None:
    if callback is not None and callback():
        raise OfficialAttentionSnapshotError("注意公告讀取／保存已取消")


@dataclass(frozen=True, slots=True)
class OfficialAttentionSnapshotPin:
    directory: Path
    manifest_sha256: str
    receipt_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.directory, Path) or not self.directory.is_absolute():
            raise OfficialAttentionSnapshotError("請明選絕對版本目錄，不搜尋latest")
        _sha(self.manifest_sha256)
        _sha(self.receipt_sha256)


@dataclass(frozen=True, slots=True)
class OfficialAttentionSnapshotRead:
    pin: OfficialAttentionSnapshotPin
    query_date: str
    stock_code: str
    rows: tuple[OfficialAttentionRow, ...]
    total_securities: int
    source_url: str
    first_persisted_at: datetime
    successful_batch_completed_at: datetime
    available_hour: datetime
    availability_basis: str = _BASIS
    source_use_accepted: bool = False
    historical_pit_eligible: bool = False


def _read(path: Path, expected: str | None, pins: list[dict[str, Any]]) -> bytes:
    target = _canonical_path(path, "attention_source", allow_missing=False)
    raw, signature = _read_exact_file(target, maximum=MAX_ATTENTION_RAW_BYTES)
    digest = _hash(raw)
    if expected is not None and digest != _sha(expected):
        raise OfficialAttentionSnapshotError("注意公告來源SHA不符：" + path.name)
    pins.append({"path": str(target), "sha256": digest, "bytes": len(raw), "signature": signature})
    return raw


def _finish(pins: list[dict[str, Any]], callback: Callable[[], bool] | None) -> None:
    for pin in pins:
        _cancel(callback)
        raw, signature = _read_exact_file(_canonical_path(Path(pin["path"]), "attention_source", allow_missing=False),
                                          maximum=min(MAX_ATTENTION_RAW_BYTES, max(1, pin["bytes"])))
        if signature != pin["signature"] or _hash(raw) != pin["sha256"]:
            raise OfficialAttentionSnapshotError("注意公告原件在讀取期間改變")


def _validate_capture(files: dict[str, bytes], query_date: date) -> tuple[OfficialAttentionReport, datetime]:
    """收據路徑只作原文；固定檔名避免跟隨外部任意路徑。"""
    meta = _json(files["http-receipt.json"], transport=True)
    result = _json(files["worker_result.json"], transport=True)
    job = _json(files["worker_job.json"], transport=True)
    expected_url = attention_query_url(query_date)
    if not isinstance(meta, dict) or not isinstance(result, dict) or not isinstance(job, dict):
        raise OfficialAttentionSnapshotError("HTTP／worker原收據必須是物件")
    required = {"schema_version": 1, "method": "GET", "official_url": expected_url, "response_url": expected_url,
                "response_status": 200, "status": "transport_complete_candidate", "candidate_complete": True,
                "response_body_complete": True, "response_body_eof": True, "deadline_exceeded": False,
                "failure_code": None, "worker_exit_code": 0, "worker_wait_reaped": True,
                "worker_process_handle_closed": True, "worker_pid_alive_after_reap": False,
                "worker_terminated_by_controller": False, "sidecar_error_code": None,
                "worker_root_named_job_membership_verified": True, "worker_root_named_job_pid_absent_after_reap": True}
    if any(type(meta.get(key)) is not type(value) or meta.get(key) != value for key, value in required.items()):
        raise OfficialAttentionSnapshotError("原HTTP非完整成功／逾時／worker未正常回收")
    raw = files["response.raw"]
    if (type(meta.get("raw_bytes")) is not int or meta["raw_bytes"] != len(raw)
            or meta.get("raw_sha256") != _hash(raw)
            or meta.get("body_completion_evidence") != f"eof:{meta.get('raw_file')}:{_hash(raw)}"
            or meta.get("content_encoding_original_values") not in ([], ["identity"])):
        raise OfficialAttentionSnapshotError("注意公告原body／EOF／編碼不符")
    lengths = meta.get("content_length_original_values")
    if not isinstance(lengths, list) or (lengths and lengths != [str(len(raw))]):
        raise OfficialAttentionSnapshotError("HTTP宣告長度不符")
    bindings = {"headers.json": "headers", "worker_input.json": "request_input", "worker_job.json": "worker_job",
                "cookies.before_request.json": "cookie_input", "cookies.after_headers.json": "cookie_output"}
    for name, prefix in bindings.items():
        if meta.get(prefix + "_sha256") != _hash(files[name]):
            raise OfficialAttentionSnapshotError("HTTP原件側錄SHA不符：" + name)
    if (result.get("body_eof") is not True or result.get("failure_code") is not None
            or result.get("raw_sha256") != _hash(raw) or type(result.get("received_body_bytes")) is not int
            or result["received_body_bytes"] != len(raw)):
        raise OfficialAttentionSnapshotError("worker原body完成證據不符")
    completed = _local(meta["ended_at"])
    started = _local(meta["started_at"])
    body_observed = _local(result["body_completed_observed_at"])
    if not started <= body_observed <= completed or query_date > started.date():
        raise OfficialAttentionSnapshotError("注意公告取得時鐘倒退或資料日超前")
    report = parse_official_attention_report(raw, query_date=query_date, observed_date=started.date())
    return report, completed


def _manifest(files: dict[str, bytes], query_date: date) -> tuple[dict[str, Any], OfficialAttentionReport]:
    if set(files) != set(_FILES) | {"documents/" + name for name in ATTENTION_DOCUMENT_PINS}:
        raise OfficialAttentionSnapshotError("注意公告完整原件鏈缺件")
    for name, digest in ATTENTION_DOCUMENT_PINS.items():
        if _hash(files["documents/" + name]) != digest:
            raise OfficialAttentionSnapshotError("官方查詢契約原件版本不符")
    report, completed = _validate_capture(files, query_date)
    meta = {"schema_version": _MANIFEST, "parser_version": ATTENTION_PARSER_VERSION,
            "query_date": query_date.isoformat(), "source_url": attention_query_url(query_date),
            "capture_completed_at": completed.isoformat(), "total_securities": report.declared_security_count,
            "total_rows": report.declared_total,
            "official_timestamp_original_text": "", "official_timestamp": None,
            "official_date_basis": "announcement_date_only",
            "source_use_accepted": False, "historical_pit_eligible": False, "formal_apply_allowed": False,
            "artifact_pins": {name: {"sha256": _hash(raw), "bytes": len(raw)} for name, raw in sorted(files.items())},
            "worker_result_hash_basis": "new_snapshot_binds_saved_bytes_not_an_original_http_receipt_hash"}
    return meta, report


def _write(path: Path, raw: bytes) -> str:
    _canonical_path(path, "attention_output", allow_missing=True)
    if os.path.lexists(path):
        raise OfficialAttentionSnapshotError("注意公告版本不可覆寫")
    _create_immutable_bytes(path, raw)
    saved, _ = _read_exact_file(_canonical_path(path, "attention_output", allow_missing=False), maximum=MAX_ATTENTION_RAW_BYTES)
    if saved != raw:
        raise OfficialAttentionSnapshotError("注意公告保存讀回不符")
    return _hash(raw)


def _barrier(directory: Path) -> None:
    if any(os.path.lexists(directory / name) for name in (".pending.json", "failure.json")):
        raise OfficialAttentionSnapshotError("注意公告批次仍pending或已失敗")


def seal_official_attention_snapshot(
    attempt_directory: Path, expected_http_receipt_sha256: str, *, query_date: date,
    documents: dict[str, Path], output_directory: Path,
    clock: Callable[[], datetime] | None = None, check_cancel: Callable[[], bool] | None = None,
) -> OfficialAttentionSnapshotPin:
    """只另存明示候選目錄；不寫正式資料、原attempt或mutable pointer。"""
    source = _canonical_path(attempt_directory, "attention_capture", allow_missing=False)
    output = _canonical_path(output_directory, "attention_output", allow_missing=True)
    for text in (os.getenv("DATA_ROOT", "F:/Min/Python/Project/FA_Data"), os.getenv("OUTPUT_ROOT"),
                 os.getenv("PERSONAL_DATA_ROOT"), os.getenv("PERSONAL_STORE_ROOT")):
        if text and output.is_relative_to(Path(text).absolute()):
            raise OfficialAttentionSnapshotError("不可在正式／私人資料根寫入注意公告候選")
    if set(documents) != set(ATTENTION_DOCUMENT_PINS):
        raise OfficialAttentionSnapshotError("請提供固定三份官方查詢契約原件")
    pins: list[dict[str, Any]] = []
    files = {name: _read(source / ("receipt.json" if name == "http-receipt.json" else name),
                        expected_http_receipt_sha256 if name == "http-receipt.json" else None, pins) for name in _FILES}
    files.update({"documents/" + name: _read(path, ATTENTION_DOCUMENT_PINS[name], pins) for name, path in documents.items()})
    manifest, _ = _manifest(files, query_date)
    _finish(pins, check_cancel)
    output.mkdir(exist_ok=False)
    (output / "documents").mkdir()
    get_clock = clock or (lambda: datetime.now(_TAIPEI))
    try:
        _write(output / ".pending.json", _bytes({"http_receipt_sha256": _sha(expected_http_receipt_sha256)}))
        for name, raw in files.items():
            _cancel(check_cancel)
            _write(output / name, raw)
        manifest_sha = _write(output / "manifest.json", _bytes(manifest))
        first = _local(get_clock())
        if first < _local(manifest["capture_completed_at"]):
            raise OfficialAttentionSnapshotError("首次版本保存不得早於實際取得完成")
        _finish(pins, check_cancel)
        completed = _local(get_clock())
        if first > completed or first.replace(minute=0, second=0, microsecond=0) != completed.replace(minute=0, second=0, microsecond=0):
            raise OfficialAttentionSnapshotError("批次保存跨小時或時鐘倒退，保留pending")
        available = _batch_publish_guard_hour(completed)
        receipt = {"schema_version": _RECEIPT, "manifest_sha256": manifest_sha, "batch_status": "success",
                   "first_persisted_at": first.isoformat(), "successful_batch_completed_at": completed.isoformat(),
                   "available_hour": available.isoformat(), "availability_basis": _BASIS,
                   "time_basis_policy": DAILY_SOURCE_TIME_BASIS_POLICY}
        receipt_sha = _write(output / "receipt.json", _bytes(receipt))
        _finish(pins, check_cancel)
        _cancel(check_cancel)
        persisted = _local(get_clock())
        if not completed <= persisted < available:
            raise OfficialAttentionSnapshotError("成功收據尚未在可用小時之前保存")
        (output / ".pending.json").unlink()
        return OfficialAttentionSnapshotPin(output, manifest_sha, receipt_sha)
    except Exception as exc:
        try:
            _write(output / "failure.json", _bytes({"success": False, "reason": str(exc)[:1024]}))
        except Exception as preserve_error:
            exc.add_note("失敗封存另有錯誤：" + str(preserve_error))
        raise


def read_official_attention_snapshot(
    pin: OfficialAttentionSnapshotPin, *, stock_code: str, decision_cutoff: datetime,
    check_cancel: Callable[[], bool] | None = None,
) -> OfficialAttentionSnapshotRead:
    """每次重驗全部原件；空列只表示此 TWSE 公告日沒有該代碼。"""
    if type(pin) is not OfficialAttentionSnapshotPin or not re.fullmatch(r"[0-9A-Z]{4,6}|\*", stock_code):
        raise OfficialAttentionSnapshotError("請明選固定版本與合法證券代號")
    cutoff = _local(decision_cutoff)
    if cutoff > datetime.now(_TAIPEI):
        raise OfficialAttentionSnapshotError("不得以未來時鐘提前讀取注意公告")
    directory = _canonical_path(pin.directory, "attention_snapshot", allow_missing=False)
    _barrier(directory)
    pins: list[dict[str, Any]] = []
    manifest = _json(_read(directory / "manifest.json", pin.manifest_sha256, pins))
    receipt = _json(_read(directory / "receipt.json", pin.receipt_sha256, pins))
    if not isinstance(manifest, dict) or not isinstance(receipt, dict):
        raise OfficialAttentionSnapshotError("注意公告manifest／receipt格式不符")
    query_date = date.fromisoformat(manifest["query_date"])
    files: dict[str, bytes] = {}
    artifacts = manifest.get("artifact_pins", {})
    if not isinstance(artifacts, dict) or set(artifacts) != set(_FILES) | {"documents/" + name for name in ATTENTION_DOCUMENT_PINS}:
        raise OfficialAttentionSnapshotError("注意公告完整原件鏈缺件")
    for name, spec in artifacts.items():
        _cancel(check_cancel)
        files[name] = _read(directory / name, spec["sha256"], pins)
    expected, report = _manifest(files, query_date)
    if manifest != expected:
        raise OfficialAttentionSnapshotError("注意公告manifest與完整原件／解析結果不符")
    first = _local(receipt["first_persisted_at"])
    completed = _local(receipt["successful_batch_completed_at"])
    available = _batch_publish_guard_hour(completed)
    expected_receipt = {"schema_version": _RECEIPT, "manifest_sha256": pin.manifest_sha256, "batch_status": "success",
                        "first_persisted_at": first.isoformat(), "successful_batch_completed_at": completed.isoformat(),
                        "available_hour": available.isoformat(), "availability_basis": _BASIS,
                        "time_basis_policy": DAILY_SOURCE_TIME_BASIS_POLICY}
    if (receipt != expected_receipt or first < _local(manifest["capture_completed_at"]) or first > completed
            or first.replace(minute=0, second=0, microsecond=0) != completed.replace(minute=0, second=0, microsecond=0)):
        raise OfficialAttentionSnapshotError("注意公告批次保存／可用小時不符")
    if cutoff < available:
        raise OfficialAttentionSnapshotError("尚未到注意公告成功批次台北可用小時：" + available.isoformat())
    _finish(pins, check_cancel)
    _barrier(directory)
    _cancel(check_cancel)
    return OfficialAttentionSnapshotRead(pin, report.query_date, stock_code,
        report.rows if stock_code == "*" else tuple(row for row in report.rows if row.stock_code == stock_code),
        report.declared_security_count, manifest["source_url"], first, completed, available)
