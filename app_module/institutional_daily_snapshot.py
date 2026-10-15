"""沿原TWSE法人capture保存成功批次時鐘，精確讀回候選事實；不授來源或PIT資格。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any, Callable
from urllib.parse import parse_qsl, urlsplit
from zoneinfo import ZoneInfo

from app_module.recommendation_portfolio_calendar_artifact_v1 import (
    _canonical_path, _file_signature, _read_exact_file, _reject_constant,
    _reject_duplicate_keys, _reject_float, _validate_json_depth,
)
from data_module.daily_source_snapshot import (
    DAILY_SOURCE_TIME_BASIS_POLICY, _batch_publish_guard_hour, _ceil_hour,
)
from data_module.institutional_credit_flows_service import (
    PARSER_VERSION, MAX_RESPONSE_BYTES, _candidate_row, _capture_scope_metadata,
    _capture_scope_specs, _parse_endpoint, _write_json_create_only,
)

_TAIPEI = ZoneInfo("Asia/Taipei")
_MANIFEST = "institutional-daily-manifest.v1"
_RECEIPT = "institutional-daily-receipt.v1"
_FLOWS = tuple(f"{group}_{suffix}" for group in ("foreign_investor", "investment_trust", "dealer")
               for suffix in ("buy", "sell", "net"))
_MAX_JSON = 32 * 1024 * 1024


class InstitutionalDailySnapshotError(ValueError):
    """來源、保存、時鐘或選定版本不合格，拒絕本次讀取。"""


def _hash(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _sha(value: str) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise InstitutionalDailySnapshotError("必須提供外部小寫SHA256")
    return value


def _local(value: datetime | str) -> datetime:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(parsed, datetime) or parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InstitutionalDailySnapshotError("批次與決策時間必須含時區")
    return parsed.astimezone(_TAIPEI)


def _cancel(callback: Callable[[], bool] | None) -> None:
    if callback is not None and callback():
        raise InstitutionalDailySnapshotError("法人批次讀取／保存已取消")


@dataclass(frozen=True, slots=True)
class InstitutionalDailySnapshotPin:
    directory: Path
    manifest_sha256: str
    receipt_sha256: str

    def __post_init__(self) -> None:
        _sha(self.manifest_sha256)
        _sha(self.receipt_sha256)
        if not isinstance(self.directory, Path) or not self.directory.is_absolute():
            raise InstitutionalDailySnapshotError("請明選絕對批次目錄，不搜尋latest")


@dataclass(frozen=True, slots=True)
class InstitutionalDailyRow:
    stock_code: str
    decision_date: str
    foreign_investor_buy: int
    foreign_investor_sell: int
    foreign_investor_net: int
    investment_trust_buy: int
    investment_trust_sell: int
    investment_trust_net: int
    dealer_buy: int
    dealer_sell: int
    dealer_net: int
    raw_sha256: str
    source_version: str
    official_timestamp_original_text: str
    official_timestamp: str | None


@dataclass(frozen=True, slots=True)
class InstitutionalDailySnapshotRead:
    pin: InstitutionalDailySnapshotPin
    stock_code: str
    rows: tuple[InstitutionalDailyRow, ...]
    total_records: int
    first_persisted_at: datetime
    successful_batch_completed_at: datetime
    available_hour: datetime
    availability_basis: str
    candidate_only: bool = True
    source_use_accepted: bool = False
    historical_pit_eligible: bool = False


def _read(path: Path, expected: str | None, maximum: int, pins: list[dict[str, Any]]) -> bytes:
    target = _canonical_path(path, "institutional_source", allow_missing=False)
    raw, signature = _read_exact_file(target, maximum=maximum)
    digest = _hash(raw)
    if expected is not None and digest != _sha(expected):
        raise InstitutionalDailySnapshotError("法人來源SHA不符：" + path.name)
    pins.append({"path": str(target), "sha256": digest, "bytes": len(raw), "signature": signature})
    return raw


def _json(raw: bytes) -> Any:
    _validate_json_depth(raw)
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys,
                      parse_constant=_reject_constant, parse_float=_reject_float)


def _finish(pins: list[dict[str, Any]], callback: Callable[[], bool] | None) -> None:
    for pin in pins:
        _cancel(callback)
        path = _canonical_path(Path(pin["path"]), "institutional_source", allow_missing=False)
        raw, signature = _read_exact_file(path, maximum=min(_MAX_JSON, max(1, pin["bytes"])))
        if signature != pin["signature"] or _hash(raw) != pin["sha256"]:
            raise InstitutionalDailySnapshotError("法人來源在讀取期間改變")


def _capture(run: Path, capture_sha: str, callback: Callable[[], bool] | None) -> tuple[dict[str, Any], list[InstitutionalDailyRow], list[dict[str, Any]]]:
    """重驗同一原capture/parser/candidate，不查SQL、不重算或擴大來源範圍。"""
    root = _canonical_path(run, "institutional_capture", allow_missing=False)
    pins: list[dict[str, Any]] = []
    manifest = _json(_read(root / "manifest.json", capture_sha, 512 * 1024, pins))
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != "institutional-credit-flows-candidate-bundle.v1"
            or manifest.get("parser_version") != PARSER_VERSION or manifest.get("candidate_only") is not True
            or manifest.get("formal_apply_allowed") is not False or manifest.get("downstream_eligibility") != "none"):
        raise InstitutionalDailySnapshotError("只接受原法人候選capture，不提升用途")
    scope = _capture_scope_metadata(date.fromisoformat(manifest["as_of_date"]), "twse_institutional")
    days = manifest.get("discovered_sessions")
    if (manifest.get("capture_scope") != scope or type(days) is not list or not 1 <= len(days) <= 30
            or any(type(day) is not str for day in days) or days != sorted(set(days))
            or type(manifest.get("session_count")) is not int or manifest.get("session_count") != len(days)):
        raise InstitutionalDailySnapshotError("必須明選完整TWSE法人範圍與原日期")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or len(sources) != len(days):
        raise InstitutionalDailySnapshotError("法人日期分區缺件或重複")
    sessions = manifest.get("sessions")
    if (not isinstance(sessions, list) or len(sessions) != len(days)
            or [item.get("decision_date") for item in sessions] != days):
        raise InstitutionalDailySnapshotError("法人原始分區品質收據缺件")
    rows: list[InstitutionalDailyRow] = []
    partitions: list[dict[str, Any]] = []
    starts: list[datetime] = []
    completes: list[datetime] = []
    for day, source in zip(days, sources):
        _cancel(callback)
        session = date.fromisoformat(day)
        spec = _capture_scope_specs(session, "twse_institutional")[0]
        raw_relative = Path("raw") / day / "twse_T86.json"
        meta_relative = Path(str(raw_relative) + ".metadata.json")
        candidate_relative = Path("candidate") / "institutional_flows" / f"{day}.json"
        quality = sessions[len(partitions)].get("merged", {}).get("institutional_flows", {})
        if (source.get("source_id") != "institutional_flows" or source.get("decision_date") != day
                or type(quality.get("quarantine_row_count")) is not int or quality.get("quarantine_row_count") != 0
                or len(source.get("raw_artifacts", [])) != 1):
            raise InstitutionalDailySnapshotError("法人分區身分或品質失敗")
        artifact = source["raw_artifacts"][0]
        if (Path(artifact["path"]) != raw_relative or Path(artifact["metadata_path"]) != meta_relative
                or Path(source["candidate_rows_path"]) != candidate_relative):
            raise InstitutionalDailySnapshotError("法人原件路徑不在固定分區")
        raw = _read(root / raw_relative, artifact["sha256"], MAX_RESPONSE_BYTES, pins)
        raw_sha = _hash(raw)
        meta = _json(_read(root / meta_relative, None, 128 * 1024, pins))
        if (not isinstance(meta, dict) or any(meta.get(key) != getattr(spec, key) for key in
                ("source_id", "market", "endpoint_id", "source_version", "quantity_unit"))
                or meta.get("requested_date") != day or meta.get("request_parameters") != dict(spec.params)
                or type(meta.get("http_status")) is not int or meta.get("http_status") != 200 or meta.get("payload_sha256") != raw_sha
                or type(meta.get("payload_size_bytes")) is not int or meta.get("payload_size_bytes") != len(raw)):
            raise InstitutionalDailySnapshotError("法人HTTP來源／單位／版本不符")
        actual_url, expected_url = urlsplit(meta.get("url", "")), urlsplit(spec.url)
        if (actual_url.scheme != "https" or actual_url.netloc != expected_url.netloc or actual_url.path != expected_url.path
                or (actual_url.query and sorted(parse_qsl(actual_url.query)) != sorted(spec.params.items()))):
            raise InstitutionalDailySnapshotError("法人endpoint不符，不自動改用其他來源")
        evidence = meta.get("transport_evidence", {})
        declared = evidence.get("declared_content_length")
        if (evidence.get("schema_version") != "flow-http-body.v1" or evidence.get("eof_observed") is not True
                or type(evidence.get("body_size_bytes")) is not int or evidence.get("body_size_bytes") != len(raw)
                or evidence.get("content_encoding") not in ("", "identity")
                or (declared is not None and (type(declared) is not int or declared != len(raw)))):
            raise InstitutionalDailySnapshotError("原HTTP缺完整EOF／長度證據，不能補認舊版本")
        capture_clock = datetime.fromisoformat(meta["completed_at"])
        completed = _local(capture_clock)
        attempts = meta.get("attempts")
        if not isinstance(attempts, list) or not attempts or len(attempts) > 16:
            raise InstitutionalDailySnapshotError("法人取得attempt時鐘缺件")
        started = min(_local(item["started_at"]) for item in attempts)
        if (started > completed or session > started.date()
                or any(_local(item["completed_at"]) > completed for item in attempts)):
            raise InstitutionalDailySnapshotError("法人取得時鐘倒退或資料日超前")
        parsed = _parse_endpoint(spec, raw, requested_date=day, completed_at=capture_clock)
        if any(type(row.get(key)) is not int or (not key.endswith("_net") and row[key] < 0)
               for row in parsed.rows for key in _FLOWS):
            raise InstitutionalDailySnapshotError("法人股數不是合法非負買賣／有號淨額整數")
        candidates = _json(_read(root / candidate_relative, source["candidate_rows_sha256"], _MAX_JSON, pins))
        expected_rows = sorted([_candidate_row(row, source_id="institutional_flows") for row in parsed.rows],
                               key=lambda row: row["values"]["stock_code"])
        if (parsed.quarantine or not expected_rows
                or json.dumps(candidates, sort_keys=True) != json.dumps(expected_rows, sort_keys=True)
                or type(source["accepted_row_count"]) is not int or source["accepted_row_count"] != len(expected_rows)
                or type(quality.get("accepted_row_count")) is not int or quality.get("accepted_row_count") != len(expected_rows)):
            raise InstitutionalDailySnapshotError("法人解析品質／原候選全文不一致")
        decoded_raw = _json(raw)
        fields = decoded_raw.get("fields")
        if (decoded_raw.get("hints") != "單位：股" or type(fields) is not list
                or any(type(field) is not str for field in fields)
                or len(fields) != len(set(fields))
                or not {"自營商買賣超股數", "三大法人買賣超股數"}.issubset(fields)):
            raise InstitutionalDailySnapshotError("原件缺股數單位或獨立宣告合計欄位，不能補認")
        original = decoded_raw.get("publicationTime")
        original = "" if original is None else original
        if type(original) is not str:
            raise InstitutionalDailySnapshotError("官方時間原文必須是字串")
        official = _local(parsed.publication_at) if parsed.publication_at is not None else None
        if official is not None and official > completed:
            raise InstitutionalDailySnapshotError("官方時間晚於實際取得完成，拒絕倒填")
        partitions.append({"decision_date": day, "raw_sha256": raw_sha, "row_count": len(expected_rows),
                           "official_timestamp_original_text": original,
                           "official_timestamp": official.isoformat() if official else None})
        for values in parsed.rows:
            rows.append(InstitutionalDailyRow(
                stock_code=values["stock_code"], decision_date=day,
                **{key: values[key] for key in _FLOWS}, raw_sha256=raw_sha, source_version=spec.source_version,
                official_timestamp_original_text=original, official_timestamp=official.isoformat() if official else None,
            ))
        starts.append(started)
        completes.append(completed)
    readback = _json(_read(root / "readback.json", None, 512 * 1024, pins))
    totals = {"institutional_flows": len(rows)}
    if (json.dumps(manifest.get("totals"), sort_keys=True) != json.dumps(totals, sort_keys=True)
            or readback.get("manifest_sha256") != capture_sha or readback.get("capture_scope") != scope
            or json.dumps(readback.get("totals"), sort_keys=True) != json.dumps(totals, sort_keys=True)):
        raise InstitutionalDailySnapshotError("原capture未完整保存讀回或總數不符")
    _finish(pins, callback)
    payload = {"schema_version": _MANIFEST, "capture_manifest_sha256": capture_sha,
               "parser_version": PARSER_VERSION, "capture_scope": scope, "partitions": partitions,
               "total_records": len(rows), "source_batch_started_at": min(starts).isoformat(),
               "capture_completed_at": max(completes).isoformat(),
               "artifact_pins": [{key: item[key] for key in ("path", "sha256", "bytes")} for item in pins],
               "candidate_only": True, "source_use_accepted": False, "historical_pit_eligible": False}
    return payload, rows, pins


def _write(path: Path, payload: object) -> str:
    _canonical_path(path, "institutional_output", allow_missing=True)
    if os.path.lexists(path):
        raise InstitutionalDailySnapshotError("法人每日版本不可覆寫")
    digest = _write_json_create_only(path, payload)
    _canonical_path(path, "institutional_output", allow_missing=False)
    raw, _ = _read_exact_file(path, maximum=512 * 1024)
    if _hash(raw) != digest:
        raise InstitutionalDailySnapshotError("法人收據寫入讀回不符")
    return digest


def _barrier(directory: Path) -> None:
    if any(os.path.lexists(directory / name) for name in (".pending.json", "failure.json")):
        raise InstitutionalDailySnapshotError("法人批次仍pending或已失敗")


def seal_twse_institutional_capture(
    run_directory: Path, expected_capture_manifest_sha256: str, *,
    clock: Callable[[], datetime] | None = None,
    check_cancel: Callable[[], bool] | None = None,
) -> InstitutionalDailySnapshotPin:
    """僅在原候選run旁寫新收據；原raw／manifest與正式DB不變。"""
    run = _canonical_path(run_directory, "institutional_capture", allow_missing=False)
    for text in (os.getenv("DATA_ROOT", "D:/Min/Python/Project/FA_Data"),
                 os.getenv("OUTPUT_ROOT"), os.getenv("PERSONAL_DATA_ROOT"), os.getenv("PERSONAL_STORE_ROOT")):
        if text and run.is_relative_to(Path(text).absolute()):
            raise InstitutionalDailySnapshotError("不可在正式／私人資料根寫入法人候選收據")
    _cancel(check_cancel)
    capture_sha = _sha(expected_capture_manifest_sha256)
    payload, _, inputs = _capture(run, capture_sha, check_cancel)
    target = run / "daily_snapshot"
    target.mkdir(exist_ok=False)
    _canonical_path(target, "institutional_output", allow_missing=False)
    get_clock = clock or (lambda: datetime.now(_TAIPEI))
    try:
        _write(target / ".pending.json", {"capture_manifest_sha256": capture_sha})
        manifest_sha = _write(target / "manifest.json", payload)
        first = _local(get_clock())
        if first < _local(payload["capture_completed_at"]):
            raise InstitutionalDailySnapshotError("首次成功版本保存早於取得完成")
        _finish(inputs, check_cancel)
        completed = _local(get_clock())
        if completed < first or completed.replace(minute=0, second=0, microsecond=0) != first.replace(minute=0, second=0, microsecond=0):
            raise InstitutionalDailySnapshotError("批次保存跨小時或時鐘倒退，保留pending")
        available = max([_batch_publish_guard_hour(completed)] + [
            _ceil_hour(_local(item["official_timestamp"])) for item in payload["partitions"] if item["official_timestamp"]
        ])
        basis = "official_timestamp_and_successful_batch_completion" if any(
            item["official_timestamp"] for item in payload["partitions"]
        ) else "successful_batch_completion_fallback"
        receipt = {"schema_version": _RECEIPT, "manifest_sha256": manifest_sha,
                   "batch_status": "success", "first_persisted_at": first.isoformat(),
                   "successful_batch_completed_at": completed.isoformat(),
                   "completion_basis": "durable_raw_candidate_manifest_and_pending_closed",
                   "available_hour": available.isoformat(), "availability_basis": basis,
                   "time_basis_policy": DAILY_SOURCE_TIME_BASIS_POLICY}
        receipt_sha = _write(target / "receipt.json", receipt)
        _finish(inputs, check_cancel)
        _cancel(check_cancel)
        persisted = _local(get_clock())
        if not completed <= persisted < available:
            raise InstitutionalDailySnapshotError("成功收據未在可用小時之前保存，保留pending")
        _cancel(check_cancel)
        (target / ".pending.json").unlink()
        return InstitutionalDailySnapshotPin(target, manifest_sha, receipt_sha)
    except Exception as exc:
        try:
            _write(target / "failure.json", {"reason": str(exc)[:1024], "success": False})
        except Exception as preservation_error:
            exc.add_note("法人批次失敗封存另有錯誤：" + str(preservation_error))
        raise


def read_twse_institutional_daily_snapshot(
    pin: InstitutionalDailySnapshotPin, *, stock_code: str, decision_cutoff: datetime,
    check_cancel: Callable[[], bool] | None = None,
) -> InstitutionalDailySnapshotRead:
    """重驗全部原件／品質，返回所選代號；不從最新DB補欄或授予連買／PIT。"""
    if type(pin) is not InstitutionalDailySnapshotPin or type(stock_code) is not str or not re.fullmatch(r"[A-Za-z0-9]{4,12}", stock_code):
        raise InstitutionalDailySnapshotError("請指定固定批次與有效證券代號")
    cutoff = _local(decision_cutoff)
    directory = _canonical_path(pin.directory, "institutional_daily", allow_missing=False)
    if directory.name != "daily_snapshot":
        raise InstitutionalDailySnapshotError("不是原法人capture的固定daily_snapshot目錄")
    _barrier(directory)
    pins: list[dict[str, Any]] = []
    manifest = _json(_read(directory / "manifest.json", pin.manifest_sha256, 512 * 1024, pins))
    receipt = _json(_read(directory / "receipt.json", pin.receipt_sha256, 128 * 1024, pins))
    if (type(receipt) is not dict or set(receipt) != {
            "schema_version", "manifest_sha256", "batch_status", "first_persisted_at",
            "successful_batch_completed_at", "completion_basis", "available_hour", "availability_basis", "time_basis_policy"}
            or receipt.get("schema_version") != _RECEIPT or receipt.get("manifest_sha256") != pin.manifest_sha256
            or receipt.get("batch_status") != "success"):
        raise InstitutionalDailySnapshotError("法人成功收據不符")
    expected, rows, source_pins = _capture(directory.parent, manifest["capture_manifest_sha256"], check_cancel)
    if manifest != expected:
        raise InstitutionalDailySnapshotError("法人daily manifest與全部原件／解析結果不符")
    first, completed = _local(receipt["first_persisted_at"]), _local(receipt["successful_batch_completed_at"])
    available = max([_batch_publish_guard_hour(completed)] + [
        _ceil_hour(_local(item["official_timestamp"])) for item in expected["partitions"] if item["official_timestamp"]
    ])
    basis = "official_timestamp_and_successful_batch_completion" if any(item["official_timestamp"] for item in expected["partitions"]) else "successful_batch_completion_fallback"
    if (first < _local(expected["capture_completed_at"]) or first > completed
            or first.replace(minute=0, second=0, microsecond=0) != completed.replace(minute=0, second=0, microsecond=0)
            or receipt.get("completion_basis") != "durable_raw_candidate_manifest_and_pending_closed"
            or receipt.get("time_basis_policy") != DAILY_SOURCE_TIME_BASIS_POLICY
            or receipt.get("available_hour") != available.isoformat() or receipt.get("availability_basis") != basis):
        raise InstitutionalDailySnapshotError("法人批次小時／保存時鐘不符")
    if cutoff < available:
        raise InstitutionalDailySnapshotError("尚未到此成功批次的台北可用小時：" + available.isoformat())
    _finish(pins + source_pins, check_cancel)
    _barrier(directory)
    _cancel(check_cancel)
    return InstitutionalDailySnapshotRead(pin, stock_code, tuple(row for row in rows if row.stock_code == stock_code),
                                          len(rows), first, completed, available, basis)
