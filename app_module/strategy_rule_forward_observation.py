"""由公開 v4 exact parent 保存與重讀前向技術規則研究觀察。

本模組沿既有公開來源 reader 將已版本化的單一 predicate 投影為三態，
以 writer 保存時鐘建立 immutable observation，再以 exact receipt 重讀。
完整來源母體與 UNKNOWN 保留；此觀察的資格為 research_only，
完整策略執行及績效資格須由後續策略生命週期與帳戶來源鏈證明。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Context, localcontext
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
from typing import Any, Literal, Mapping

from app_module.personal_data_paths import PersonalDataPathError, _absolute, _reject_links

from app_module.daily_market_technical_method_contract_v4 import (
    daily_market_technical_method_contract_v4_payload,
    daily_market_technical_method_contract_v4_sha256,
    validate_daily_market_technical_method_contract_v4,
)
from app_module.rule_research_technical_parent_capture_v4 import (
    read_daily_market_technical_parent_capture_v4,
)


OBSERVATION_SCHEMA = "p08-forward-strategy-signal-observation.v1"
SAVED_SCHEMA = "p08-forward-strategy-signal-saved.v1"
RECEIPT_SCHEMA = "p08-forward-strategy-signal-receipt.v1"
SIGNAL_STATES = frozenset({"match", "no_match", "unknown"})
MAX_CAPTURE_BYTES = 2 * 1024 * 1024
MAX_CAPTURE_COUNT = 256
MAX_RETAINED_BYTES = 64 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
# 既有技術規則產物在標準 Decimal context 下生成。重讀時固定還原 Python
# 預設精度與捨入，避免呼叫端 context 改變來源語義。
_SOURCE_DECIMAL_CONTEXT = Context(prec=28)


class StrategySignalObservationError(ValueError):
    """來源、時鐘或 immutable observation 不符合契約。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise StrategySignalObservationError(code)


def _reject_float_tree(value: object) -> None:
    if isinstance(value, float):
        _require(False, "signal_observation_float_forbidden")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_float_tree(key)
            _reject_float_tree(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _reject_float_tree(item)


def _canonical(value: object) -> bytes:
    _reject_float_tree(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise StrategySignalObservationError("signal_observation_json_invalid") from exc


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def _parse_aware(value: object, code: str) -> datetime:
    if not isinstance(value, str) or len(value) > 80:
        raise StrategySignalObservationError(code)
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise StrategySignalObservationError(code) from exc
    _require(result.tzinfo is not None and result.utcoffset() is not None, code)
    return result.astimezone(timezone.utc)


def _utc_now() -> datetime:
    """僅由本 writer 讀取系統 UTC；API 不接受 caller clock。"""

    return datetime.now(timezone.utc)


def _canonical_root(value: str | Path, code: str) -> Path:
    try:
        supplied = Path(value).expanduser()
        _require(supplied.is_absolute(), code)
        _reject_links(supplied)
        return _absolute(supplied)
    except (OSError, RuntimeError, TypeError, ValueError, PersonalDataPathError) as exc:
        raise StrategySignalObservationError(code) from exc


def _file_signature(info: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_nlink,
        getattr(info, "st_file_attributes", 0),
    )


def _has_reparse_alias(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _check_directory(path: Path, code: str, *, required: bool = True) -> bool:
    try:
        _reject_links(path)
        info = os.stat(path, follow_symlinks=False)
    except FileNotFoundError:
        _require(not required, code)
        return False
    except (OSError, PersonalDataPathError) as exc:
        raise StrategySignalObservationError(code) from exc
    _require(stat.S_ISDIR(info.st_mode) and not _has_reparse_alias(info), code)
    return True


def _read_bounded_regular_file(path: Path, *, limit: int, code: str) -> bytes:
    """以有界串流讀取單一 regular file，拒絕硬連結、reparse 與競態替換。"""

    try:
        _reject_links(path)
        _absolute(path)
        before = os.stat(path, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise StrategySignalObservationError("signal_observation_capture_missing") from exc
    except (OSError, PersonalDataPathError) as exc:
        raise StrategySignalObservationError(code) from exc
    _require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and not _has_reparse_alias(before), code)
    _require(before.st_size <= limit, "signal_observation_capture_byte_limit")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise StrategySignalObservationError(code) from exc
    opened: os.stat_result | None = None
    after_fd: os.stat_result | None = None
    try:
        opened = os.fstat(descriptor)
        _require(
            stat.S_ISREG(opened.st_mode)
            and opened.st_nlink == 1
            and not _has_reparse_alias(opened)
            and _file_signature(opened) == _file_signature(before),
            "signal_observation_capture_changed_during_read",
        )
        chunks: list[bytes] = []
        total = 0
        while total <= limit:
            chunk = os.read(descriptor, min(65_536, limit + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        _require(total <= limit, "signal_observation_capture_byte_limit")
        after_fd = os.fstat(descriptor)
    except OSError as exc:
        raise StrategySignalObservationError(code) from exc
    finally:
        os.close(descriptor)
    try:
        _reject_links(path)
        after_path = os.stat(path, follow_symlinks=False)
    except (OSError, PersonalDataPathError) as exc:
        raise StrategySignalObservationError("signal_observation_capture_changed_during_read") from exc
    _require(
        opened is not None
        and after_fd is not None
        and _file_signature(opened) == _file_signature(after_fd)
        and _file_signature(after_fd) == _file_signature(after_path),
        "signal_observation_capture_changed_during_read",
    )
    return b"".join(chunks)


def _disjoint_roots(left: Path, right: Path) -> None:
    _require(
        left != right and not left.is_relative_to(right) and not right.is_relative_to(left),
        "signal_observation_source_output_overlap",
    )


def _read_parent(
    parent_output_root: str | Path,
    plan_identity_sha256: str,
    receipt_identity_sha256: str,
    expected_receipt_sha256: str,
    expected_plan_sha256: str,
) -> tuple[Path, dict[str, Any]]:
    _require(_is_sha(plan_identity_sha256), "signal_observation_parent_plan_pin_invalid")
    _require(_is_sha(receipt_identity_sha256), "signal_observation_parent_receipt_pin_invalid")
    _require(_is_sha(expected_receipt_sha256), "signal_observation_parent_receipt_hash_invalid")
    _require(_is_sha(expected_plan_sha256), "signal_observation_parent_plan_hash_invalid")
    parent_root = _canonical_root(parent_output_root, "signal_observation_parent_root_invalid")
    try:
        with localcontext(_SOURCE_DECIMAL_CONTEXT):
            package = read_daily_market_technical_parent_capture_v4(
                parent_root,
                plan_identity_sha256,
                receipt_identity_sha256,
                expected_receipt_sha256=expected_receipt_sha256,
                expected_plan_sha256=expected_plan_sha256,
            )
    except Exception as exc:
        raise StrategySignalObservationError("signal_observation_parent_exact_read_failed") from exc
    _require(isinstance(package, dict) and set(package) == {
        "plan", "plan_sha256", "receipt", "receipt_sha256"
    }, "signal_observation_parent_package_invalid")
    _require(
        package["plan_sha256"] == expected_plan_sha256
        and package["receipt_sha256"] == expected_receipt_sha256,
        "signal_observation_parent_exact_pin_mismatch",
    )
    plan = package["plan"]
    receipt = package["receipt"]
    _require(isinstance(plan, dict) and isinstance(receipt, dict), "signal_observation_parent_package_invalid")
    _require(receipt.get("status") == "complete", "signal_observation_parent_not_complete")
    _require(receipt.get("parent_plan_identity_sha256") == plan_identity_sha256,
             "signal_observation_parent_plan_mismatch")
    return parent_root, package


def _rule_binding(plan: Mapping[str, Any], rule_key: str) -> dict[str, Any]:
    _require(isinstance(rule_key, str) and bool(rule_key), "signal_observation_rule_key_invalid")
    contracts = plan.get("method_contracts")
    contracts_sha = plan.get("method_contracts_sha256")
    if not isinstance(contracts, Mapping):
        raise StrategySignalObservationError("signal_observation_method_contract_invalid")
    try:
        validated = validate_daily_market_technical_method_contract_v4(
            contracts, expected_sha256=contracts_sha
        )
    except Exception as exc:
        raise StrategySignalObservationError("signal_observation_method_contract_invalid") from exc
    _require(
        contracts_sha == daily_market_technical_method_contract_v4_sha256()
        and _canonical(validated) == _canonical(daily_market_technical_method_contract_v4_payload()),
        "signal_observation_method_contract_not_current_exact_version",
    )
    rules = contracts.get("rules")
    if not isinstance(rules, (list, tuple)):
        raise StrategySignalObservationError("signal_observation_method_contract_invalid")
    selected = [item for item in rules if isinstance(item, Mapping) and item.get("key") == rule_key]
    _require(len(selected) == 1, "signal_observation_rule_unknown_or_duplicate")
    item = selected[0]
    _require(
        isinstance(item.get("method_id"), str)
        and bool(item.get("method_id"))
        and isinstance(item.get("version"), str)
        and bool(item.get("version"))
        and isinstance(item.get("parameters"), Mapping),
        "signal_observation_rule_contract_invalid",
    )
    return {
        "rule_key": rule_key,
        "method_id": item["method_id"],
        "rule_version": item["version"],
        "parameters": dict(item["parameters"]),
        "method_contract_sha256": str(contracts_sha),
    }


def _signals_from_verified_parent(
    package: Mapping[str, Any],
    binding: Mapping[str, Any],
) -> list[dict[str, str]]:
    plan = package["plan"]
    cohort = plan.get("cohort")
    evidence = plan.get("source_stock_evidence")
    if not isinstance(cohort, Mapping):
        raise StrategySignalObservationError("signal_observation_cohort_invalid")
    included = cohort.get("included_stock_codes")
    if not isinstance(included, list):
        raise StrategySignalObservationError("signal_observation_cohort_invalid")
    _require(
        all(isinstance(code, str) and code for code in included)
        and included == sorted(set(included)),
        "signal_observation_cohort_members_invalid",
    )
    if not isinstance(evidence, list) or len(evidence) != len(included):
        raise StrategySignalObservationError("signal_observation_source_evidence_incomplete")
    by_code: dict[str, Mapping[str, Any]] = {}
    for item in evidence:
        _require(isinstance(item, Mapping), "signal_observation_source_evidence_invalid")
        code = item.get("stock_code")
        _require(isinstance(code, str) and code not in by_code,
                 "signal_observation_source_evidence_duplicate")
        by_code[code] = item
    _require(tuple(by_code) == tuple(included), "signal_observation_source_evidence_membership_mismatch")

    rows: list[dict[str, str]] = []
    for code in included:
        item = by_code[code]
        states = item.get("rule_states")
        if not isinstance(states, Mapping):
            raise StrategySignalObservationError("signal_observation_source_rule_states_invalid")
        state = states.get(binding["rule_key"])
        _require(state in SIGNAL_STATES, "signal_observation_signal_enum_invalid")
        # 合法的 per-stock unknown 必須保留，不把缺值改成 no_match 或丟掉該股。
        rows.append({
            "stock_code": code,
            "state": str(state),
            "snapshot_identity_sha256": str(item.get("snapshot_identity_sha256", "")),
            "source_window_fingerprint_sha256": str(item.get("source_window_fingerprint_sha256", "")),
            "raw_source_window_fingerprint_sha256": str(item.get("raw_source_window_fingerprint_sha256", "")),
        })
    return rows


def _identity(payload: Mapping[str, Any]) -> str:
    return _sha(_canonical({key: value for key, value in payload.items()
                           if key != "capture_identity_sha256"}))


def _validate_artifact(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise StrategySignalObservationError("signal_observation_artifact_invalid")
    value = payload
    _require(set(value) == {
        "schema_version", "capture_identity_sha256", "observation_kind", "qualification",
        "rule_binding", "source_binding", "clock", "signals",
    }, "signal_observation_artifact_fields_invalid")
    _require(value["schema_version"] == OBSERVATION_SCHEMA
             and value["observation_kind"] == "research_observation",
             "signal_observation_artifact_schema_invalid")
    _require(value["qualification"] == {
        "research_only": True,
        "historical_pit_eligible": False,
        "execution_eligible": False,
        "performance_eligible": False,
        "source_availability": "unknown",
        "calendar_event_clock": "unknown",
    }, "signal_observation_qualification_invalid")
    _require(isinstance(value["rule_binding"], dict), "signal_observation_rule_binding_invalid")
    _require(isinstance(value["source_binding"], dict), "signal_observation_source_binding_invalid")
    _require(isinstance(value["clock"], dict), "signal_observation_clock_invalid")
    _require(set(value["clock"]) == {
        "source_decision_cutoff", "source_receipt_completed_at", "captured_at",
        "source_availability", "historical_pit_eligible",
    }, "signal_observation_clock_fields_invalid")
    _require(isinstance(value["signals"], list), "signal_observation_signals_invalid")
    _require(_is_sha(value["capture_identity_sha256"])
             and _identity(value) == value["capture_identity_sha256"],
             "signal_observation_identity_mismatch")
    clock = value["clock"]
    captured = _parse_aware(clock.get("captured_at"), "signal_observation_capture_clock_invalid")
    source_cutoff = _parse_aware(clock.get("source_decision_cutoff"), "signal_observation_source_cutoff_invalid")
    source_completed = _parse_aware(
        clock.get("source_receipt_completed_at"), "signal_observation_parent_clock_invalid"
    )
    _require(captured >= source_completed >= source_cutoff, "signal_observation_clock_order_invalid")
    _require(clock.get("source_availability") == "unknown"
             and clock.get("historical_pit_eligible") is False,
             "signal_observation_source_clock_qualification_invalid")
    rows = value["signals"]
    codes: list[str] = []
    for row in rows:
        _require(isinstance(row, dict) and set(row) == {
            "stock_code", "state", "snapshot_identity_sha256",
            "source_window_fingerprint_sha256", "raw_source_window_fingerprint_sha256",
        }, "signal_observation_signal_row_invalid")
        code = row["stock_code"]
        _require(isinstance(code, str) and bool(code) and len(code) <= 16,
                 "signal_observation_signal_stock_invalid")
        _require(row["state"] in SIGNAL_STATES, "signal_observation_signal_enum_invalid")
        for key in ("snapshot_identity_sha256", "source_window_fingerprint_sha256",
                    "raw_source_window_fingerprint_sha256"):
            _require(_is_sha(row[key]), "signal_observation_signal_source_pin_invalid")
        codes.append(code)
    _require(codes == sorted(set(codes)), "signal_observation_signal_duplicate_or_order_invalid")
    source = value["source_binding"]
    for key in ("plan_identity_sha256", "plan_sha256", "receipt_identity_sha256",
                "receipt_sha256", "generation_identity_sha256", "cohort_identity_sha256",
                "source_clock_identity_sha256", "method_contract_sha256"):
        _require(_is_sha(source.get(key)), "signal_observation_source_pin_invalid")
    _require(isinstance(source.get("parent_output_root"), str)
             and Path(source["parent_output_root"]).is_absolute(),
             "signal_observation_parent_root_invalid")
    _require(isinstance(source.get("universe_id"), str) and bool(source["universe_id"])
             and isinstance(source.get("population_version"), str) and bool(source["population_version"]),
             "signal_observation_universe_identity_invalid")
    return value


@dataclass(frozen=True, slots=True)
class StrategySignalObservationDTO:
    """經 public parent exact reader 與保存 artifact 共同核驗的研究觀察。"""

    capture_identity_sha256: str
    receipt_sha256: str
    saved_at: str
    available_at: str
    rule_key: str
    method_id: str
    rule_version: str
    universe_id: str
    population_version: str
    decision_cutoff: str
    signals_json: str
    qualification: Literal["research_only"] = "research_only"

    @property
    def signals(self) -> tuple[dict[str, str], ...]:
        return tuple(json.loads(self.signals_json))

    def to_dict(self) -> dict[str, Any]:
        return {
            "capture_identity_sha256": self.capture_identity_sha256,
            "receipt_sha256": self.receipt_sha256,
            "saved_at": self.saved_at,
            "available_at": self.available_at,
            "rule_key": self.rule_key,
            "method_id": self.method_id,
            "rule_version": self.rule_version,
            "universe_id": self.universe_id,
            "population_version": self.population_version,
            "decision_cutoff": self.decision_cutoff,
            "signals": list(self.signals),
            "qualification": self.qualification,
        }


@dataclass(frozen=True, slots=True)
class StrategySignalObservationWriteResult:
    capture_identity_sha256: str
    artifact_sha256: str
    receipt_sha256: str
    receipt_path: str
    captured_at: str
    saved_at: str
    available_at: str
    signal_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "capture_identity_sha256": self.capture_identity_sha256,
            "artifact_sha256": self.artifact_sha256,
            "receipt_sha256": self.receipt_sha256,
            "receipt_path": self.receipt_path,
            "captured_at": self.captured_at,
            "saved_at": self.saved_at,
            "available_at": self.available_at,
            "signal_count": self.signal_count,
        }


def _write_new(path: Path, raw: bytes, *, limit: int) -> None:
    _require(len(raw) <= limit, "signal_observation_artifact_byte_limit")
    _check_directory(path.parent, "signal_observation_output_root_invalid")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise StrategySignalObservationError("signal_observation_duplicate_capture") from exc
    except OSError as exc:
        raise StrategySignalObservationError("signal_observation_write_failed") from exc


def write_forward_signal_observation_from_exact_parent(
    *,
    parent_output_root: str | Path,
    plan_identity_sha256: str,
    expected_plan_sha256: str,
    receipt_identity_sha256: str,
    expected_receipt_sha256: str,
    rule_key: str,
    output_root: str | Path,
) -> StrategySignalObservationWriteResult:
    """重開 exact public parent，保存指定既有 rule 的 forward observation。

    API 不接受 DataFrame、score、target、fill 或 caller clock。訊號來源只能
    是 exact parent reader 核驗後的完整 source_stock_evidence。
    """

    parent_root, package = _read_parent(
        parent_output_root,
        plan_identity_sha256,
        receipt_identity_sha256,
        expected_receipt_sha256,
        expected_plan_sha256,
    )
    plan = package["plan"]
    receipt = package["receipt"]
    binding = _rule_binding(plan, rule_key)
    signals = _signals_from_verified_parent(package, binding)
    source_clock = plan.get("source_clock")
    cohort = plan.get("cohort")
    _require(isinstance(source_clock, Mapping) and isinstance(cohort, Mapping),
             "signal_observation_parent_scope_invalid")
    cutoff_raw = source_clock.get("decision_cutoff")
    cutoff = _parse_aware(cutoff_raw, "signal_observation_source_cutoff_invalid")
    parent_completed_at = _parse_aware(receipt.get("observed_at"), "signal_observation_parent_clock_invalid")
    captured = _utc_now()
    _require(captured >= parent_completed_at >= cutoff, "signal_observation_capture_before_source_readback")
    parent_binding = {
        "parent_output_root": str(parent_root),
        "plan_identity_sha256": plan_identity_sha256,
        "plan_sha256": expected_plan_sha256,
        "receipt_identity_sha256": receipt_identity_sha256,
        "receipt_sha256": expected_receipt_sha256,
        "generation_identity_sha256": str(plan.get("generation_identity_sha256", "")),
        "cohort_identity_sha256": str(plan.get("cohort", {}).get("cohort_identity_sha256", "")),
        "universe_id": str(cohort.get("universe_id", "")),
        "population_version": str(cohort.get("population_version", "")),
        "included_stock_codes": list(cohort.get("included_stock_codes", [])),
        "excluded_stock_codes": list(cohort.get("excluded_stock_codes", [])),
        "source_clock_identity_sha256": str(plan.get("source_clock_identity_sha256", "")),
        "method_contract_sha256": binding["method_contract_sha256"],
    }
    artifact: dict[str, Any] = {
        "schema_version": OBSERVATION_SCHEMA,
        "observation_kind": "research_observation",
        "qualification": {
            "research_only": True,
            "historical_pit_eligible": False,
            "execution_eligible": False,
            "performance_eligible": False,
            "source_availability": "unknown",
            "calendar_event_clock": "unknown",
        },
        "rule_binding": binding,
        "source_binding": parent_binding,
        "clock": {
            "source_decision_cutoff": str(cutoff_raw),
            "source_receipt_completed_at": str(receipt["observed_at"]),
            "captured_at": captured.isoformat(),
            "source_availability": "unknown",
            "historical_pit_eligible": False,
        },
        "signals": signals,
    }
    artifact["capture_identity_sha256"] = _identity(artifact)
    artifact = _validate_artifact(artifact)
    artifact_raw = _canonical(artifact)
    artifact_sha = _sha(artifact_raw)
    _require(len(artifact_raw) <= MAX_CAPTURE_BYTES, "signal_observation_artifact_byte_limit")

    root = _canonical_root(output_root, "signal_observation_output_root_invalid")
    _disjoint_roots(root, parent_root)
    root_exists = _check_directory(root, "signal_observation_output_root_invalid", required=False)
    if not root_exists:
        _check_directory(root.parent, "signal_observation_output_root_invalid")
    probe = root if root_exists else root.parent
    _require(probe.exists() and shutil.disk_usage(probe).free >= 2 * MAX_CAPTURE_BYTES,
             "signal_observation_capacity_insufficient")
    observations_root = root / "observations"
    entries: list[Path] = []
    observations_exist = _check_directory(
        observations_root, "signal_observation_output_root_invalid", required=False
    ) if root_exists else False
    if observations_exist:
        try:
            with os.scandir(observations_root) as iterator:
                for entry in iterator:
                    entries.append(Path(entry.path))
                    _require(len(entries) <= MAX_CAPTURE_COUNT,
                             "signal_observation_capture_count_limit")
        except OSError as exc:
            raise StrategySignalObservationError("signal_observation_store_entry_invalid") from exc
        for directory in entries:
            _check_directory(directory, "signal_observation_store_entry_invalid")
        _require(len(entries) < MAX_CAPTURE_COUNT, "signal_observation_capture_count_limit")
        retained = 0
        for directory in entries:
            file_count = 0
            try:
                with os.scandir(directory) as iterator:
                    for entry in iterator:
                        file_count += 1
                        _require(file_count <= 3 and entry.name in {
                            "observation.json", "saved.json", "receipt.json"
                        }, "signal_observation_store_entry_invalid")
                        item = Path(entry.path)
                        _reject_links(item)
                        info = os.stat(item, follow_symlinks=False)
                        _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                                 and not _has_reparse_alias(info),
                                 "signal_observation_store_entry_invalid")
                        retained += info.st_size
            except (OSError, PersonalDataPathError) as exc:
                raise StrategySignalObservationError("signal_observation_store_entry_invalid") from exc
        _require(retained + len(artifact_raw) + 8192 <= MAX_RETAINED_BYTES,
                 "signal_observation_retention_limit")
    try:
        observations_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise StrategySignalObservationError("signal_observation_output_root_invalid") from exc
    _check_directory(root, "signal_observation_output_root_invalid")
    _check_directory(observations_root, "signal_observation_output_root_invalid")
    capture_dir = root / "observations" / artifact["capture_identity_sha256"]
    try:
        capture_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise StrategySignalObservationError("signal_observation_duplicate_capture") from exc
    except OSError as exc:
        raise StrategySignalObservationError("signal_observation_output_root_invalid") from exc
    _check_directory(capture_dir, "signal_observation_output_root_invalid")
    artifact_path = capture_dir / "observation.json"
    _write_new(artifact_path, artifact_raw, limit=MAX_CAPTURE_BYTES)

    # 先確認 observation 完整寫入並讀回，再建立 writer-owned saved clock。
    persisted_raw = _read_bounded_regular_file(
        artifact_path, limit=MAX_CAPTURE_BYTES, code="signal_observation_artifact_readback_failed"
    )
    _require(persisted_raw == artifact_raw and _sha(persisted_raw) == artifact_sha,
             "signal_observation_artifact_readback_mismatch")
    saved = _utc_now()
    _require(saved >= captured, "signal_observation_writer_clock_order_invalid")
    saved_body = {
        "schema_version": SAVED_SCHEMA,
        "capture_identity_sha256": artifact["capture_identity_sha256"],
        "artifact_sha256": artifact_sha,
        "saved_at": saved.isoformat(),
    }
    saved_raw = _canonical(saved_body)
    saved_path = capture_dir / "saved.json"
    _write_new(saved_path, saved_raw, limit=4096)
    saved_reread = _read_bounded_regular_file(
        saved_path, limit=4096, code="signal_observation_saved_readback_failed"
    )
    _require(saved_reread == saved_raw and _sha(saved_reread) == _sha(saved_raw),
             "signal_observation_saved_readback_mismatch")

    # available_at 只在完整 observation 與 saved receipt 均已讀回後取樣；
    # 最終 receipt 隨後發布，作為 exact reader 的完整性封套。
    available = _utc_now()
    _require(available >= saved >= captured, "signal_observation_writer_clock_order_invalid")
    receipt_body = {
        "schema_version": RECEIPT_SCHEMA,
        "capture_identity_sha256": artifact["capture_identity_sha256"],
        "artifact_sha256": artifact_sha,
        "saved_receipt_sha256": _sha(saved_raw),
        "saved_at": saved.isoformat(),
        "available_at": available.isoformat(),
        "status": "complete",
    }
    receipt_raw = _canonical(receipt_body)
    receipt_path = capture_dir / "receipt.json"
    _write_new(receipt_path, receipt_raw, limit=4096)
    receipt_reread_raw = _read_bounded_regular_file(
        receipt_path, limit=4096, code="signal_observation_receipt_readback_failed"
    )
    _require(receipt_reread_raw == receipt_raw, "signal_observation_receipt_readback_mismatch")
    receipt_reread = read_exact_forward_signal_observation(
        output_root=root,
        capture_identity_sha256=artifact["capture_identity_sha256"],
        expected_receipt_sha256=_sha(receipt_raw),
        rule_key=rule_key,
        decision_cutoff=available,
    )
    _require(receipt_reread.capture_identity_sha256 == artifact["capture_identity_sha256"],
             "signal_observation_receipt_readback_mismatch")
    return StrategySignalObservationWriteResult(
        capture_identity_sha256=artifact["capture_identity_sha256"],
        artifact_sha256=artifact_sha,
        receipt_sha256=_sha(receipt_raw),
        receipt_path=str(receipt_path),
        captured_at=captured.isoformat(),
        saved_at=saved.isoformat(),
        available_at=available.isoformat(),
        signal_count=len(signals),
    )


def read_exact_forward_signal_observation(
    *,
    output_root: str | Path,
    capture_identity_sha256: str,
    expected_receipt_sha256: str,
    rule_key: str,
    decision_cutoff: datetime,
    expected_universe_id: str | None = None,
    expected_population_version: str | None = None,
) -> StrategySignalObservationDTO:
    """以 exact parent public reader 重算並讀取一份可用的 forward observation。"""

    _require(_is_sha(capture_identity_sha256), "signal_observation_capture_pin_invalid")
    _require(_is_sha(expected_receipt_sha256), "signal_observation_receipt_pin_invalid")
    _require(isinstance(decision_cutoff, datetime)
             and decision_cutoff.tzinfo is not None and decision_cutoff.utcoffset() is not None,
             "signal_observation_decision_cutoff_naive")
    decision_utc = decision_cutoff.astimezone(timezone.utc)
    root = _canonical_root(output_root, "signal_observation_output_root_invalid")
    _check_directory(root, "signal_observation_output_root_invalid")
    observations_root = root / "observations"
    _check_directory(observations_root, "signal_observation_capture_path_invalid")
    capture_dir = root / "observations" / capture_identity_sha256
    _check_directory(capture_dir, "signal_observation_capture_path_invalid")
    artifact_path = capture_dir / "observation.json"
    saved_path = capture_dir / "saved.json"
    receipt_path = capture_dir / "receipt.json"
    artifact_raw = _read_bounded_regular_file(
        artifact_path, limit=MAX_CAPTURE_BYTES, code="signal_observation_capture_path_invalid"
    )
    saved_raw = _read_bounded_regular_file(
        saved_path, limit=4096, code="signal_observation_saved_receipt_invalid"
    )
    receipt_raw = _read_bounded_regular_file(
        receipt_path, limit=4096, code="signal_observation_receipt_invalid"
    )
    _require(_sha(receipt_raw) == expected_receipt_sha256,
             "signal_observation_receipt_hash_mismatch")
    try:
        artifact = json.loads(artifact_raw.decode("utf-8"), parse_constant=lambda _item: (_ for _ in ()).throw(ValueError()))
        saved_receipt = json.loads(saved_raw.decode("utf-8"), parse_constant=lambda _item: (_ for _ in ()).throw(ValueError()))
        receipt = json.loads(receipt_raw.decode("utf-8"), parse_constant=lambda _item: (_ for _ in ()).throw(ValueError()))
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise StrategySignalObservationError("signal_observation_json_invalid") from exc
    _require(_canonical(artifact) == artifact_raw, "signal_observation_artifact_noncanonical")
    _require(_canonical(saved_receipt) == saved_raw, "signal_observation_saved_receipt_noncanonical")
    _require(_canonical(receipt) == receipt_raw, "signal_observation_receipt_noncanonical")
    artifact = _validate_artifact(artifact)
    _require(artifact["capture_identity_sha256"] == capture_identity_sha256,
             "signal_observation_capture_identity_mismatch")
    _require(isinstance(saved_receipt, dict) and set(saved_receipt) == {
        "schema_version", "capture_identity_sha256", "artifact_sha256", "saved_at"
    } and saved_receipt["schema_version"] == SAVED_SCHEMA,
             "signal_observation_saved_receipt_invalid")
    _require(isinstance(receipt, dict) and set(receipt) == {
        "schema_version", "capture_identity_sha256", "artifact_sha256", "saved_receipt_sha256",
        "saved_at", "available_at", "status"
    } and receipt["schema_version"] == RECEIPT_SCHEMA and receipt["status"] == "complete",
             "signal_observation_receipt_invalid")
    _require(saved_receipt["capture_identity_sha256"] == capture_identity_sha256
             and saved_receipt["artifact_sha256"] == _sha(artifact_raw),
             "signal_observation_saved_receipt_artifact_mismatch")
    saved = _parse_aware(saved_receipt["saved_at"], "signal_observation_saved_clock_invalid")
    _require(receipt["capture_identity_sha256"] == capture_identity_sha256
             and receipt["artifact_sha256"] == _sha(artifact_raw)
             and receipt["saved_receipt_sha256"] == _sha(saved_raw)
             and receipt["saved_at"] == saved_receipt["saved_at"],
             "signal_observation_receipt_artifact_mismatch")
    available = _parse_aware(receipt["available_at"], "signal_observation_available_clock_invalid")
    captured = _parse_aware(artifact["clock"]["captured_at"], "signal_observation_capture_clock_invalid")
    _require(available >= saved >= captured, "signal_observation_clock_order_invalid")
    _require(available <= datetime.now(timezone.utc), "signal_observation_available_clock_in_future")
    _require(decision_utc >= available, "signal_observation_not_available_at_decision")

    source = artifact["source_binding"]
    if expected_universe_id is not None:
        _require(source["universe_id"] == expected_universe_id,
                 "signal_observation_foreign_universe")
    if expected_population_version is not None:
        _require(source["population_version"] == expected_population_version,
                 "signal_observation_foreign_population_version")
    binding = _rule_binding({"method_contracts": daily_market_technical_method_contract_v4_payload(),
                             "method_contracts_sha256": source["method_contract_sha256"]}, rule_key)
    _require(artifact["rule_binding"] == binding, "signal_observation_rule_binding_mismatch")
    parent_root, package = _read_parent(
        source["parent_output_root"],
        source["plan_identity_sha256"],
        source["receipt_identity_sha256"],
        source["receipt_sha256"],
        source["plan_sha256"],
    )
    _disjoint_roots(root, parent_root)
    plan = package["plan"]
    cohort = plan["cohort"]
    _require(plan["generation_identity_sha256"] == source["generation_identity_sha256"]
             and plan["source_clock_identity_sha256"] == source["source_clock_identity_sha256"]
             and cohort["cohort_identity_sha256"] == source["cohort_identity_sha256"]
             and cohort["universe_id"] == source["universe_id"]
             and cohort["population_version"] == source["population_version"]
             and cohort["included_stock_codes"] == source["included_stock_codes"]
             and cohort["excluded_stock_codes"] == source["excluded_stock_codes"],
             "signal_observation_foreign_or_changed_parent")
    parent_source_clock = plan.get("source_clock")
    artifact_clock = artifact["clock"]
    _require(isinstance(parent_source_clock, Mapping), "signal_observation_parent_clock_invalid")
    actual_cutoff_raw = parent_source_clock.get("decision_cutoff")
    actual_completed_raw = package["receipt"].get("observed_at")
    _require(artifact_clock["source_decision_cutoff"] == actual_cutoff_raw
             and artifact_clock["source_receipt_completed_at"] == actual_completed_raw,
             "signal_observation_source_clock_binding_mismatch")
    actual_cutoff = _parse_aware(actual_cutoff_raw, "signal_observation_source_cutoff_invalid")
    actual_completed = _parse_aware(actual_completed_raw, "signal_observation_parent_clock_invalid")
    _require(captured >= actual_completed >= actual_cutoff,
             "signal_observation_capture_before_source_readback")
    _require(plan["method_contracts_sha256"] == source["method_contract_sha256"],
             "signal_observation_method_contract_source_mismatch")
    expected_signals = _signals_from_verified_parent(package, binding)
    _require(artifact["signals"] == expected_signals,
             "signal_observation_signal_source_mismatch")
    _require(_sha(artifact_raw) == _sha(_canonical(_validate_artifact(artifact))),
             "signal_observation_artifact_readback_mismatch")
    return StrategySignalObservationDTO(
        capture_identity_sha256=capture_identity_sha256,
        receipt_sha256=expected_receipt_sha256,
        saved_at=saved.isoformat(),
        available_at=available.isoformat(),
        rule_key=binding["rule_key"],
        method_id=binding["method_id"],
        rule_version=binding["rule_version"],
        universe_id=str(source["universe_id"]),
        population_version=str(source["population_version"]),
        decision_cutoff=artifact["clock"]["source_decision_cutoff"],
        signals_json=_canonical(expected_signals).decode("utf-8"),
    )


__all__ = [
    "StrategySignalObservationDTO",
    "StrategySignalObservationError",
    "StrategySignalObservationWriteResult",
    "read_exact_forward_signal_observation",
    "write_forward_signal_observation_from_exact_parent",
]
