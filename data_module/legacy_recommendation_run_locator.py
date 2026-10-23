"""唯讀定位有限舊推薦副本；原件資格另需獨立證據，不建立通用 D/F 別名。"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
from typing import Literal, cast


CustodyVerificationTier = Literal[
    "tier1_independent_pre_migration_file_sha256",
    "tier2_pre_migration_db_index_and_twstock_event_hash",
    "tier3_pre_migration_db_index_only_no_independent_file_sha256",
]

ALL_LEGACY_RECOMMENDATION_CUSTODY_TIERS: tuple[CustodyVerificationTier, ...] = (
    "tier1_independent_pre_migration_file_sha256",
    "tier2_pre_migration_db_index_and_twstock_event_hash",
    "tier3_pre_migration_db_index_only_no_independent_file_sha256",
)

LEGACY_RECOMMENDATION_RUN_LOCATOR_PROFILE_PATH = Path(__file__).with_name(
    "legacy_recommendation_run_locators_20261022.json"
)
LEGACY_RECOMMENDATION_RUN_LOCATOR_PROFILE_SHA256 = (
    "sha256:ed6e6184e5f16e999b630a2fe1e1dc68754ecdbf8de6662bb202d7c536a6a0fb"
)
PINNED_MIGRATION_RECEIPT_DB_SHA256 = (
    "sha256:a923447ab75e8cba5e328f95b80e4f6f0a5d241282e80cbaff0a312ba90b03aa"
)
EXPECTED_PINNED_ENTRY_COUNT = 88
MAX_LOCATOR_PROFILE_BYTES = 128 * 1024
MAX_LOCATED_LEGACY_RUN_BYTES = 8 * 1024 * 1024
_REPARSE_ATTRIBUTE = 0x400


@dataclass(frozen=True, slots=True)
class _GitOriginalRecommendationPin:
    """搬遷前既有 Git 文件原物件，與本次定位清冊分開固定。"""

    result_id: str
    commit: str
    document_path: str
    blob_id: str
    raw_sha256: str
    size_bytes: int
    statement_kind: str


_GIT_ORIGINAL_PINS = {
    "scheduled_rec_20260906_051003": _GitOriginalRecommendationPin(
        "scheduled_rec_20260906_051003",
        "542a37456d84cef5f1bf8b9edc91b27bd6c7960c",
        "docs/09_archive/V4_AUTOMATED_REVIEW_2026_09_07.md",
        "8669bfe52e141cd9a7de2a79f250d781b89817f5",
        "sha256:6ac2cd46d8a529f546653be6e41b4a52ab0e3e13409e0c3e4305dae619b7074f",
        157069, "paper_queue_source_recommendation",
    ),
    "scheduled_rec_20260907_051003": _GitOriginalRecommendationPin(
        "scheduled_rec_20260907_051003",
        "542a37456d84cef5f1bf8b9edc91b27bd6c7960c",
        "docs/09_archive/V4_AUTOMATED_REVIEW_2026_09_07.md",
        "8669bfe52e141cd9a7de2a79f250d781b89817f5",
        "sha256:6ac2cd46d8a529f546653be6e41b4a52ab0e3e13409e0c3e4305dae619b7074f",
        157069, "paper_preview_recommendation",
    ),
    "scheduled_rec_20260910_051003": _GitOriginalRecommendationPin(
        "scheduled_rec_20260910_051003",
        "5c6eee9581bf09f0e074413ebc931fa08bfd6070",
        "docs/06_qa/NATURAL_LEARNING_TRACE_2026_09_18.md",
        "a342994c41d0537206751897a3e0d203a059b59f",
        "sha256:4a20318354aa4d31aaddc69e30dbf37474503d104f74d10ab215eb93e436d1b9",
        15398, "natural_learning_source_snapshot",
    ),
    "scheduled_rec_20260914_051003": _GitOriginalRecommendationPin(
        "scheduled_rec_20260914_051003",
        "ec19e9db439512d9cd8b33e9a287e6bf57b77ac6",
        "docs/09_archive/DAILY_BANKTAIWAN_OPERATIONAL_2026_09_14_HISTORY.md",
        "67950552f067fc9369f02e2a4e09d8d1d973b84c",
        "sha256:fd025f5199640454428d2dd170806385c9ed8a5223d9318da13737b737b23ee5",
        10241, "banktaiwan_source_path_and_hash",
    ),
    "scheduled_rec_20260915_051003": _GitOriginalRecommendationPin(
        "scheduled_rec_20260915_051003",
        "0aaf0dffeb99224aa3f51f2bc58f29606a1002d9",
        "docs/06_qa/BANKTAIWAN_FIRST_SCHEDULED_RUN_FAILURE_2026_09_15.md",
        "975516839f72689bfb0ebfabaf0467d85d3df49d",
        "sha256:928e2c6a63d71bda2ea99e1f9a8137641e6dd4962bb997a90ed00250ae291dca",
        12208, "banktaiwan_snapshot_and_pinned_receipt",
    ),
    "scheduled_rec_20260917_051002": _GitOriginalRecommendationPin(
        "scheduled_rec_20260917_051002",
        "d8ce9add897575a8cb3036a85c4a73217ad338b7",
        "docs/09_archive/DECISION_EVIDENCE_CAPTURE_CLOCK_QA_2026_09_16.md",
        "63399bbc9f55e169caf30d333fb75ddc7a9e7c20",
        "sha256:6662e4c48c59a8426f1a054320c40e6b472372150ca65786078cbb5d56b277c9",
        53241, "capture_clock_recommendation_source",
    ),
    "scheduled_rec_20260921_051002": _GitOriginalRecommendationPin(
        "scheduled_rec_20260921_051002",
        "caa55f551d39f73f944a2fc2355a27a5199cc87c",
        "docs/06_qa/FORMAL_SCHEDULER_READINESS_AUDIT_2026_09_20.md",
        "ec35c157dbf1416f5528e4133b03ff61f67035f7",
        "sha256:3781a7fb86c5eae603c4ab2179ad39bc9d458a015d78868283dbbfe2301ea5d7",
        21901, "formal_scheduler_source_identity",
    ),
}

_BANKTAIWAN_0915_RECEIPT_PATH = Path(
    r"F:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\scheduled\recommendation_learning_banktaiwan\runs\2026-09-15-attempt-002-848408b70b64.json"
)
_BANKTAIWAN_0915_RECEIPT_SHA256 = "sha256:3a4e38a0bb0ecfa54f405936814350231536b32cb030f9d806fb9c92eff945cd"
_BANKTAIWAN_0915_RECEIPT_BYTES = 3425408


def _read_original_git_document(pin: _GitOriginalRecommendationPin) -> bytes | None:
    """只讀固定 commit 的原 blob；不讀工作樹副本，也不接受可變分支名稱。"""

    executable = Path(r"C:\Program Files\Git\cmd\git.exe") if os.name == "nt" else Path("/usr/bin/git")
    if not executable.is_file():
        return None
    environment = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    base_arguments = [str(executable), "-c", "core.fsmonitor=false", "cat-file"]
    object_name = f"{pin.commit}:{pin.document_path}"
    try:
        size_result = subprocess.run(
            [*base_arguments, "-s", object_name],
            cwd=Path(__file__).resolve().parents[1], env=environment,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=5, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if size_result.returncode != 0 or size_result.stdout.strip() != str(pin.size_bytes).encode("ascii"):
            return None
        result = subprocess.run(
            [*base_arguments, "blob", object_name],
            cwd=Path(__file__).resolve().parents[1], env=environment,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=5, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0 or len(result.stdout) != pin.size_bytes:
        return None
    raw = result.stdout
    if "sha256:" + hashlib.sha256(raw).hexdigest() != pin.raw_sha256:
        return None
    git_blob = b"blob " + str(len(raw)).encode("ascii") + b"\x00" + raw
    if hashlib.sha1(git_blob).hexdigest() != pin.blob_id:
        return None
    return raw


def _verify_original_git_custody(entry: Mapping[str, object]) -> bool:
    """驗原文件完整具名陳述；同一雜湊出現在其他來源或備註不取得資格。"""

    pin = _GIT_ORIGINAL_PINS.get(str(entry["result_id"]))
    if pin is None or entry["result_id"] != pin.result_id:
        return False
    origin = str(entry["origin_path"])
    original_sha = str(entry.get("independent_pre_migration_file_sha256") or entry.get("relocated_file_sha256"))
    if origin != rf"D:\Min\Python\Project\FA_Data\output\recommendation\runs\{pin.result_id}.json":
        return False
    if original_sha != entry["relocated_file_sha256"]:
        return False
    raw = _read_original_git_document(pin)
    if raw is None:
        return False
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return False
    if pin.statement_kind == "paper_preview_recommendation":
        expected = (
            f"- Recommendation：`{origin}`，file hash `{original_sha}`，5 rows，"
            "decision date `2026-09-07`。"
        )
    elif pin.statement_kind == "paper_queue_source_recommendation":
        return sum(
            lines[index] == "- source recommendation："
            and lines[index + 1] == f"  `{origin}`，"
            and lines[index + 2] == f"  file hash `{original_sha}`；"
            for index in range(len(lines) - 2)
        ) == 1
    elif pin.statement_kind == "natural_learning_source_snapshot":
        expected = (
            f"| recommendation source snapshot | `{origin}`；"
            "`created_at=2026-09-10T05:10:03-07:00`；"
            f"bytes SHA-256 `{original_sha}`。 |"
        )
    elif pin.statement_kind == "banktaiwan_source_path_and_hash":
        return sum(
            lines[index] == f"- path：`{origin}`"
            and lines[index + 1] == f"- file hash：`{original_sha}`"
            for index in range(len(lines) - 1)
        ) == 1
    elif pin.statement_kind == "capture_clock_recommendation_source":
        expected = (
            f"| recommendation source | `{origin}`；file hash `{original_sha}`；"
            "`available_at=created_at=2026-09-17T05:10:02-07:00` | "
            "source bytes 在 candidate decision 前已可用。 |"
        )
    elif pin.statement_kind == "formal_scheduler_source_identity":
        identity = (
            f"其 `result_id={pin.result_id}`、`created_at=2026-09-21T05:10:02-07:00`、"
            "`decision_date=2026-09-21`、`decision_at=2026-09-21T12:10:22.626235+00:00`；"
            f"檔案 SHA256 為 `{original_sha}`"
        )
        return sum(
            lines[index - 2] == f"`{origin}`" and lines[index - 1] == ""
            and line.partition("。")[0] == identity
            and line.partition("。")[2].startswith("snapshot cohort 共 200 rows，")
            for index, line in enumerate(lines) if index >= 2
        ) == 1
    elif pin.statement_kind == "banktaiwan_snapshot_and_pinned_receipt":
        expected_snapshot = (
            "前置 dry-run 結果為 exit `0`：官方交易日判定 `true`、snapshot `verified`，"
            f"snapshot hash 仍為 `{original_sha}`，成本情境為 `banktaiwan-electronic-estimate`／"
            "`sha256:73ad38fa8a5cd983535f50fcaf99e168aea44400ac2e7428d58400a21f55e450`，"
            "且 `shadow_only=true`、`formal_order_allowed=false`。"
        )
        expected_receipt = (
            "| operational receipt | `D:\\Min\\Python\\Project\\FA_Data_Shadow_BankTaiwan\\scheduled\\"
            "recommendation_learning_banktaiwan\\runs\\2026-09-15-attempt-002-848408b70b64.json`；"
            f"SHA-256 `{_BANKTAIWAN_0915_RECEIPT_SHA256}` |"
        )
        return (
            lines.count(expected_snapshot) == 1 and lines.count(expected_receipt) == 1
            and _verify_banktaiwan_0915_original_receipt(origin, original_sha)
        )
    else:
        return False
    return lines.count(expected) == 1


def _verify_banktaiwan_0915_original_receipt(origin: str, original_sha: str) -> bool:
    """原 Git 文件固定 operational receipt 原 bytes，再讀精確 snapshot 身份。"""

    raw = _read_pinned_profile_target_bytes(
        _BANKTAIWAN_0915_RECEIPT_PATH,
        expected_sha256=_BANKTAIWAN_0915_RECEIPT_SHA256,
        expected_size=_BANKTAIWAN_0915_RECEIPT_BYTES,
    )
    if raw is None:
        return False
    try:
        payload = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, ValueError, TypeError):
        return False
    if not isinstance(payload, dict) or not isinstance(payload.get("snapshot"), dict):
        return False
    snapshot = payload["snapshot"]
    return (
        snapshot.get("path") == origin and snapshot.get("file_sha256") == original_sha
        and snapshot.get("status") == "verified"
    )


@dataclass(frozen=True, slots=True)
class LocatedLegacyRecommendationRun:
    """單筆副本定位 envelope，明確區分實際 custody 驗證與稽核聲明。"""

    result_id: str
    origin_path: str
    current_path: Path
    raw_payload: bytes
    relocated_file_sha256: str
    relocated_size_bytes: int
    db_row_sha256: str
    custody_verification_tier: CustodyVerificationTier
    independent_pre_migration_file_sha256: str | None
    independent_pre_migration_evidence_ref: str
    custody_verified: bool = False
    research_only: bool = True


@dataclass(frozen=True, slots=True)
class LegacyRecommendationCustodyEvidencePin:
    """由呼叫端明確接受的獨立原件證據；清冊自身雜湊不構成此授權。"""

    evidence_path: Path
    evidence_sha256: str
    evidence_size_bytes: int
    record_pointer: tuple[str, ...]
    result_id_field: str
    origin_path_field: str
    original_sha256_field: str


def _verify_independent_custody(
    entry: Mapping[str, object], pin: LegacyRecommendationCustodyEvidencePin | None,
) -> bool:
    """讀回外部固定的完整原件身份記錄，不以任意文字中的雜湊命中代替。"""

    if pin is None or not _valid_sha256(pin.evidence_sha256):
        return False
    if (
        type(pin.evidence_size_bytes) is not int
        or not 0 < pin.evidence_size_bytes <= MAX_LOCATED_LEGACY_RUN_BYTES
        or not pin.evidence_path.is_absolute()
        or Path(os.path.abspath(pin.evidence_path)) == Path(os.path.abspath(str(entry["current_path"])))
        or not all(type(key) is str and key for key in pin.record_pointer)
        or not all(type(key) is str and key for key in (
            pin.result_id_field, pin.origin_path_field, pin.original_sha256_field,
        ))
    ):
        return False
    content = _read_pinned_profile_target_bytes(
        pin.evidence_path,
        expected_sha256=pin.evidence_sha256,
        expected_size=pin.evidence_size_bytes,
    )
    if content is None:
        return False
    try:
        record: object = json.loads(
            content.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
        )
        for key in pin.record_pointer:
            if not isinstance(record, dict):
                return False
            record = record[key]
    except (UnicodeDecodeError, ValueError, TypeError, KeyError):
        return False
    return isinstance(record, dict) and (
        record.get(pin.result_id_field) == entry["result_id"]
        and record.get(pin.origin_path_field) == entry["origin_path"]
        and record.get(pin.original_sha256_field) == entry["relocated_file_sha256"]
        and entry["independent_pre_migration_file_sha256"] == entry["relocated_file_sha256"]
    )


def compute_legacy_runs_db_row_sha256(
    *,
    result_id: str,
    result_name: str | None,
    regime: str | None,
    stock_count: int | None,
    config: str | None,
    notes: str | None,
    created_at: str | None,
    data_path: str,
) -> str:
    """計算 recommendation_runs.db runs 資料列的 canonical SHA-256。"""

    canonical = json.dumps(
        {
            "result_id": result_id,
            "result_name": result_name,
            "regime": regime,
            "stock_count": stock_count,
            "config": config,
            "notes": notes,
            "created_at": created_at,
            "data_path": data_path,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("定位清單含重複 JSON 欄位")
        result[key] = value
    return result


def _reject_json_constant(_: str) -> object:
    raise ValueError("定位清單含非法 JSON 常數")


def _valid_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(ch in "0123456789abcdef" for ch in value[7:])
    )


def _read_verified_locator_profile() -> list[dict[str, object]] | None:
    """讀取外部 SHA 固定且內容受限的 88 筆舊推薦結果定位清單。"""

    path = LEGACY_RECOMMENDATION_RUN_LOCATOR_PROFILE_PATH
    if not _plain_target_ancestors(path):
        return None
    try:
        before = _lstat(path)
    except OSError:
        return None
    if (
        not stat.S_ISREG(before.st_mode)
        or _is_reparse(path, before)
        or before.st_nlink != 1
        or before.st_size < 0
        or before.st_size > MAX_LOCATOR_PROFILE_BYTES
    ):
        return None
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None
    try:
        opened_before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened_before.st_mode)
            or opened_before.st_nlink != 1
            or _is_reparse(path, opened_before)
            or _identity(opened_before) != _identity(before)
        ):
            return None
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            content = handle.read(MAX_LOCATOR_PROFILE_BYTES + 1)
        opened_after = os.fstat(descriptor)
        try:
            after = _lstat(path)
        except OSError:
            return None
        if (
            len(content) > MAX_LOCATOR_PROFILE_BYTES
            or _identity(opened_after) != _identity(opened_before)
            or _identity(after) != _identity(before)
            or not stat.S_ISREG(after.st_mode)
            or _is_reparse(path, after)
            or after.st_nlink != 1
            or not _plain_target_ancestors(path)
            or "sha256:" + hashlib.sha256(content).hexdigest()
            != LEGACY_RECOMMENDATION_RUN_LOCATOR_PROFILE_SHA256
        ):
            return None
    finally:
        os.close(descriptor)
    try:
        payload = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "database_migration_receipt_path",
        "database_migration_receipt_sha256",
        "entries",
    }:
        return None
    if payload.get("schema_version") != "legacy-recommendation-run-locators.v1":
        return None
    if payload.get("database_migration_receipt_sha256") != PINNED_MIGRATION_RECEIPT_DB_SHA256:
        return None
    entries = payload.get("entries")
    if not isinstance(entries, list) or len(entries) != EXPECTED_PINNED_ENTRY_COUNT:
        return None
    result_ids: set[str] = set()
    origins: set[str] = set()
    currents: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "result_id",
            "origin_path",
            "current_path",
            "relocated_file_sha256",
            "relocated_size_bytes",
            "db_row_sha256",
            "custody_verification_tier",
            "independent_pre_migration_file_sha256",
            "independent_pre_migration_evidence_ref",
        }:
            return None
        result_id = entry.get("result_id")
        origin = entry.get("origin_path")
        current = entry.get("current_path")
        relocated_sha = entry.get("relocated_file_sha256")
        size = entry.get("relocated_size_bytes")
        db_row_sha = entry.get("db_row_sha256")
        tier = entry.get("custody_verification_tier")
        ind_sha = entry.get("independent_pre_migration_file_sha256")
        ev_ref = entry.get("independent_pre_migration_evidence_ref")
        if (
            not isinstance(result_id, str)
            or not result_id
            or not isinstance(origin, str)
            or not isinstance(current, str)
            or not _valid_sha256(relocated_sha)
            or type(size) is not int
            or size <= 0
            or size > MAX_LOCATED_LEGACY_RUN_BYTES
            or not _valid_sha256(db_row_sha)
            or tier not in ALL_LEGACY_RECOMMENDATION_CUSTODY_TIERS
            or not isinstance(ev_ref, str)
            or not ev_ref
            or result_id in result_ids
            or origin in origins
            or current in currents
        ):
            return None
        if tier == "tier1_independent_pre_migration_file_sha256":
            if not _valid_sha256(ind_sha) or ind_sha != relocated_sha:
                return None
        else:
            if ind_sha is not None:
                return None
        result_ids.add(result_id)
        origins.add(origin)
        currents.add(current)
    return entries


def locate_legacy_recommendation_run(
    result_id: str,
    origin_data_path: str | Path,
    *,
    runs_root: Path,
    db_row_sha256: str | None = None,
    allowed_tiers: Collection[str] | None = None,
    custody_evidence: Mapping[str, LegacyRecommendationCustodyEvidencePin] | None = None,
) -> LocatedLegacyRecommendationRun | None:
    """一般 consumer 僅接受另有外部原件證據且精確綁定 DB 列的搬遷結果。"""

    return _locate_legacy_recommendation_run(
        result_id, origin_data_path, runs_root=runs_root,
        db_row_sha256=db_row_sha256, allowed_tiers=allowed_tiers,
        custody_evidence=custody_evidence, audit_only=False,
    )


def audit_legacy_recommendation_run(
    result_id: str, origin_data_path: str | Path, *, runs_root: Path,
    db_row_sha256: str,
) -> LocatedLegacyRecommendationRun | None:
    """明示稽核入口只提供當前副本 envelope，不授原件 custody 或 consumer 資格。"""

    return _locate_legacy_recommendation_run(
        result_id, origin_data_path, runs_root=runs_root,
        db_row_sha256=db_row_sha256,
        allowed_tiers=ALL_LEGACY_RECOMMENDATION_CUSTODY_TIERS,
        custody_evidence=None, audit_only=True,
    )


def _locate_legacy_recommendation_run(
    result_id: str, origin_data_path: str | Path, *, runs_root: Path,
    db_row_sha256: str | None, allowed_tiers: Collection[str] | None,
    custody_evidence: Mapping[str, LegacyRecommendationCustodyEvidencePin] | None,
    audit_only: bool,
) -> LocatedLegacyRecommendationRun | None:

    if type(result_id) is not str or not result_id:
        return None
    try:
        origin_text = os.fspath(origin_data_path)
    except TypeError:
        return None
    if not isinstance(origin_text, str):
        return None
    permitted_tiers = (
        {"tier1_independent_pre_migration_file_sha256"}
        if allowed_tiers is None
        else set(allowed_tiers)
    )
    if not permitted_tiers.issubset(ALL_LEGACY_RECOMMENDATION_CUSTODY_TIERS):
        return None
    entries = _read_verified_locator_profile()
    if entries is None:
        return None
    entry = next(
        (
            candidate
            for candidate in entries
            if candidate.get("result_id") == result_id
            and candidate.get("origin_path") == origin_text
        ),
        None,
    )
    if entry is None:
        return None
    tier = cast(CustodyVerificationTier, entry["custody_verification_tier"])
    if tier not in permitted_tiers and result_id not in _GIT_ORIGINAL_PINS:
        return None
    if not _valid_sha256(db_row_sha256) or entry.get("db_row_sha256") != db_row_sha256:
        return None
    target = Path(str(entry["current_path"]))
    expected_in_root = Path(os.path.abspath(runs_root)) / f"{result_id}.json"
    if Path(os.path.abspath(target)) != expected_in_root:
        return None
    verified = False
    if not audit_only:
        if tier != "tier1_independent_pre_migration_file_sha256" and result_id not in _GIT_ORIGINAL_PINS:
            return None
        supplied_pin = (custody_evidence or {}).get(result_id)
        verified = (
            _verify_independent_custody(entry, supplied_pin)
            if supplied_pin is not None
            else _verify_original_git_custody(entry)
        )
        if not verified:
            return None

    origin_path = Path(origin_text)
    try:
        _lstat(origin_path)
    except FileNotFoundError:
        pass
    except OSError:
        return None
    else:
        return None

    expected_sha256 = str(entry["relocated_file_sha256"])
    expected_size = int(cast(int, entry["relocated_size_bytes"]))
    payload = _read_pinned_profile_target_bytes(
        target,
        expected_sha256=expected_sha256,
        expected_size=expected_size,
    )
    if payload is None:
        return None
    ind_sha = cast(
        str | None,
        entry["independent_pre_migration_file_sha256"]
        if entry.get("independent_pre_migration_file_sha256") is not None
        else (entry["relocated_file_sha256"] if verified else None),
    )
    return LocatedLegacyRecommendationRun(
        result_id=result_id,
        origin_path=origin_text,
        current_path=target,
        raw_payload=payload,
        relocated_file_sha256=expected_sha256,
        relocated_size_bytes=expected_size,
        db_row_sha256=str(entry["db_row_sha256"]),
        custody_verification_tier=tier,
        independent_pre_migration_file_sha256=ind_sha,
        independent_pre_migration_evidence_ref=str(
            entry["independent_pre_migration_evidence_ref"]
        ),
        custody_verified=verified,
        research_only=not verified,
    )


def _read_pinned_profile_target_bytes(
    path: Path,
    *,
    expected_sha256: str,
    expected_size: int,
) -> bytes | None:
    """驗證清單目標為普通單連結檔，並核對穩定讀取前後的身分與 SHA。"""

    if not _plain_target_ancestors(path):
        return None
    try:
        before = _lstat(path)
    except OSError:
        return None
    if (
        not stat.S_ISREG(before.st_mode)
        or _is_reparse(path, before)
        or before.st_nlink != 1
        or before.st_size != expected_size
        or before.st_size <= 0
        or before.st_size > MAX_LOCATED_LEGACY_RUN_BYTES
    ):
        return None
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None
    try:
        opened_before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened_before.st_mode)
            or opened_before.st_nlink != 1
            or _is_reparse(path, opened_before)
            or _identity(opened_before) != _identity(before)
        ):
            return None
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            content = handle.read(MAX_LOCATED_LEGACY_RUN_BYTES + 1)
        opened_after = os.fstat(descriptor)
        try:
            after = _lstat(path)
        except OSError:
            return None
        if (
            len(content) != expected_size
            or _identity(opened_after) != _identity(opened_before)
            or _identity(after) != _identity(before)
            or not stat.S_ISREG(after.st_mode)
            or _is_reparse(path, after)
            or after.st_nlink != 1
            or not _plain_target_ancestors(path)
        ):
            return None
        if "sha256:" + hashlib.sha256(content).hexdigest() != expected_sha256:
            return None
        return content
    finally:
        os.close(descriptor)


def _lstat(path: Path) -> os.stat_result:
    return path.lstat()


def _identity(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        int(metadata.st_dev),
        int(metadata.st_ino),
        int(metadata.st_size),
        int(getattr(metadata, "st_mtime_ns", int(metadata.st_mtime * 1_000_000_000))),
        int(getattr(metadata, "st_ctime_ns", int(metadata.st_ctime * 1_000_000_000))),
        int(metadata.st_nlink),
    )


def _is_reparse(path: Path, metadata: os.stat_result) -> bool:
    return path.is_symlink() or bool(
        getattr(metadata, "st_file_attributes", 0) & _REPARSE_ATTRIBUTE
    )


def _plain_target_ancestors(path: Path) -> bool:
    anchor = Path(path.anchor)
    try:
        metadata = _lstat(anchor)
    except OSError:
        return False
    if not stat.S_ISDIR(metadata.st_mode) or _is_reparse(anchor, metadata):
        return False
    current = anchor
    for component in path.parts[1:-1]:
        if component in ("", ".", ".."):
            return False
        current = current / component
        try:
            metadata = _lstat(current)
        except OSError:
            return False
        if not stat.S_ISDIR(metadata.st_mode) or _is_reparse(current, metadata):
            return False
    return True


load_pinned_legacy_recommendation_locators = _read_verified_locator_profile


__all__ = (
    "ALL_LEGACY_RECOMMENDATION_CUSTODY_TIERS",
    "CustodyVerificationTier",
    "EXPECTED_PINNED_ENTRY_COUNT",
    "LEGACY_RECOMMENDATION_RUN_LOCATOR_PROFILE_PATH",
    "LEGACY_RECOMMENDATION_RUN_LOCATOR_PROFILE_SHA256",
    "LocatedLegacyRecommendationRun",
    "LegacyRecommendationCustodyEvidencePin",
    "audit_legacy_recommendation_run",
    "PINNED_MIGRATION_RECEIPT_DB_SHA256",
    "compute_legacy_runs_db_row_sha256",
    "load_pinned_legacy_recommendation_locators",
    "locate_legacy_recommendation_run",
)
