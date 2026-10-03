"""建立支援市場修訂的隔離研究原始候選（Revision-Aware Research Raw Candidate）。

本模組落實 ML revision-aware rebuild 方案中的最小工程缺口：
1. 定義明確 revision-aware research 輸入契約：包含 snapshot DB identity、
   revision markers/receipts pins、market source custody 與實際 availability、
   code/schema identity 及隔離的 repo-local output/custody root。
2. 保持嚴格研究限制與安全標記：research_only=true、candidate_only=true、
   formal_dataset=false、formal_credit=false、formal_historical_PIT=false、
   formal_oos=false、promotion_eligible=false、unit_claimed=false。
3. 具備決策 cutoff 與未來函數（lookahead bias）防護，嚴格要求 Decimal/整數 scale，
   禁止任何裸 float 持久化。
4. 建置前後執行 snapshot DB 與來源 custody 的不可變性核實（immutability check），
   建置完成後執行逐 shard 串流讀回校驗（readback verification）。
5. 絕不寫入正式 D: 資料根目錄或 release_v4 pointer。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4
from zoneinfo import ZoneInfo

from data_module.contracts.source_revision import (
    SourceEvidenceNamespaceV1,
    SourceEvidencePresenceV1,
    ValidatedEvidenceFileV1,
    ValidatedNamespaceEvidenceV1,
)
from data_module.ml_research_output_boundary import (
    MLResearchOutputBoundaryError,
    resolve_ml_research_output_path,
)
from data_module.ml_daily_price_revision_gate import (
    load_verified_current_restated_source_context,
)


REVISION_AWARE_RAW_SCHEMA_VERSION = "ml-revision-aware-raw-candidate.v1"
REVISION_AWARE_COMPLETION_SCHEMA_VERSION = (
    "ml-revision-aware-raw-completion.v1"
)

TAIPEI_TZ = ZoneInfo("Asia/Taipei")
CUTOFF_TIME = time(8, 30)

MAX_CANDIDATE_BYTES = 2 << 30  # 2 GiB
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_ROW_BYTES = 128 * 1024
MIN_FREE_BYTES = 100 * 1024 * 1024  # 100 MiB safety reserve

_DECIMAL_DIGITS_LIMIT = 38
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}\Z")
_SYMBOL_PATTERN = re.compile(r"^\d{4}\Z")

# 禁止寫入的正式/生產根目錄關鍵字
_PROHIBITED_SUBSTRINGS = (
    "fa_data",
    "release_v4",
    "formal_technical_repair_receipts",
    "formal_market_repair_receipts",
)


class RevisionAwareCandidateError(ValueError):
    """Revision-aware research raw candidate 建置或校驗失敗。"""


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _aware_utc(dt: datetime, field_name: str) -> datetime:
    if not isinstance(dt, datetime) or dt.tzinfo is None or dt.utcoffset() is None:
        raise RevisionAwareCandidateError(f"{field_name} must be a timezone-aware datetime")
    return dt.astimezone(timezone.utc)


def _parse_decision_at(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return _aware_utc(value, "decision_at")
    if not isinstance(value, str) or not value.strip():
        raise RevisionAwareCandidateError("decision_at must be a non-empty string or datetime")
    cleaned = value.strip()
    # 支援 YYYY-MM-DD
    if len(cleaned) == 10 and cleaned.count("-") == 2:
        try:
            d = date.fromisoformat(cleaned)
            dt = datetime.combine(d, CUTOFF_TIME, tzinfo=TAIPEI_TZ)
            return dt.astimezone(timezone.utc)
        except ValueError as exc:
            raise RevisionAwareCandidateError(f"invalid decision_at date: {value}") from exc
    try:
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise RevisionAwareCandidateError("timestamp must include an explicit timezone")
        return dt.astimezone(timezone.utc)
    except RevisionAwareCandidateError:
        raise
    except ValueError as exc:
        raise RevisionAwareCandidateError(f"invalid decision_at format: {value}") from exc


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def _file_fingerprint(path: Path) -> dict[str, Any]:
    st = path.stat()
    return {
        "path": str(path.resolve()),
        "size_bytes": st.st_size,
        "mtime_ns": getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)),
        "sha256": _sha256_file(path),
    }


def _reject_links(path: Path, root: Path, label: str) -> None:
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError) as exc:
        raise RevisionAwareCandidateError(f"{label} cannot be resolved: {path}") from exc
    # 檢查自身與父目錄是否有 symlink
    curr: Path | None = path
    while curr is not None and curr != curr.parent:
        if curr.is_symlink():
            raise RevisionAwareCandidateError(f"{label} contains symlink: {curr}")
        if curr == root:
            break
        curr = curr.parent


def _check_isolation(path: Path, label: str) -> None:
    """確保輸出目錄不位於正式 D: 資料根目錄或 release_v4。"""
    normalized = str(path.resolve()).replace("\\", "/").casefold()
    if normalized.startswith("d:/min/python/project/fa_data") or "fa_data" in normalized:
        raise RevisionAwareCandidateError(
            f"{label} cannot target formal data root: {path}"
        )
    for prohibited in _PROHIBITED_SUBSTRINGS:
        if f"/{prohibited}/" in normalized or normalized.endswith(f"/{prohibited}") or f":/{prohibited}" in normalized:
            raise RevisionAwareCandidateError(
                f"{label} attempts to target prohibited formal path: {path}"
            )


def _resolve_research_path(path: Path, label: str) -> Path:
    """所有正式 caller 都使用 repository 的固定 research allowlist。"""
    try:
        return resolve_ml_research_output_path(path)
    except MLResearchOutputBoundaryError as exc:
        raise RevisionAwareCandidateError(f"{label}: {exc}") from exc


def _strict_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RevisionAwareCandidateError(f"{field_name} must be an integer (bool is not accepted)")
    return value


def _strict_numeric_integer(value: Any, scale: int, field_name: str) -> int:
    """Decimal/int 轉成標準十進位 exponent；拒絕 float、非有限值與靜默截斷。"""
    if isinstance(value, bool) or isinstance(value, float):
        raise RevisionAwareCandidateError(f"{field_name} must not be bool or float")
    try:
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise RevisionAwareCandidateError(f"{field_name} is not a valid Decimal") from exc
    if not decimal_value.is_finite():
        raise RevisionAwareCandidateError(f"{field_name} must be finite")
    scaled = decimal_value * (Decimal(10) ** scale)
    if scaled != scaled.to_integral_value():
        raise RevisionAwareCandidateError(f"{field_name} has precision beyond exponent {scale}")
    return int(scaled)


def _normalize_source_date(value: Any, field_name: str) -> date:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise RevisionAwareCandidateError(f"{field_name} must be YYYYMMDD or YYYY-MM-DD")
    raw = str(value)
    try:
        if re.fullmatch(r"\d{8}", raw):
            return datetime.strptime(raw, "%Y%m%d").date()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            return date.fromisoformat(raw)
    except ValueError as exc:
        raise RevisionAwareCandidateError(f"{field_name} is an invalid calendar date") from exc
    raise RevisionAwareCandidateError(f"{field_name} must be exact YYYYMMDD or YYYY-MM-DD")


def _assert_no_float(obj: Any, context: str = "") -> None:
    """嚴格防止浮點數注入。"""
    if isinstance(obj, float):
        raise RevisionAwareCandidateError(
            f"naked float detected in {context}: {obj}; Decimal or scaled integer required"
        )
    if isinstance(obj, dict):
        for k, v in obj.items():
            _assert_no_float(v, f"{context}.{k}")
    elif isinstance(obj, (list, tuple)):
        for idx, item in enumerate(obj):
            _assert_no_float(item, f"{context}[{idx}]")


@dataclass(frozen=True)
class RevisionAwareRawRequest:
    """Revision-aware research raw candidate 建置請求。"""

    snapshot_db: Path
    output_dir: Path
    custody_dir: Path
    decision_at: str | datetime
    history_start_date: str = "2014-01-01"
    symbols: tuple[str, ...] | None = None
    years: tuple[int, ...] | None = None
    expected_snapshot_sha256: str | None = None
    snapshot_context_receipt_path: Path | None = None
    expected_snapshot_context_receipt_sha256: str | None = None
    market_revision_receipts_dir: Path | None = None
    source_custody_manifests: tuple[Path, ...] = ()
    expected_source_manifest_hashes: Mapping[str, str] = field(default_factory=dict)
    preview_only: bool = False
    now_provider: Callable[[], datetime] | None = None

    def __post_init__(self) -> None:
        if not self.snapshot_db.exists():
            raise RevisionAwareCandidateError(f"snapshot_db does not exist: {self.snapshot_db}")
        if not self.snapshot_db.is_file():
            raise RevisionAwareCandidateError(f"snapshot_db is not a regular file: {self.snapshot_db}")
        _resolve_research_path(self.output_dir, "output_dir")
        _resolve_research_path(self.custody_dir, "custody_dir")


@dataclass(frozen=True)
class RevisionAwareRawResult:
    """Revision-aware research raw candidate 建置產物。"""

    status: str
    manifest_path: Path
    manifest_hash: str
    manifest_file_sha256: str
    shards: tuple[dict[str, Any], ...]
    row_count: int
    feature_value_count: int
    input_pins: dict[str, Any]
    safety: dict[str, Any]
    completion_receipt_path: Path | None = None

    @property
    def shard_count(self) -> int:
        return len(self.shards)


class RevisionAwareRawCandidateBuilder:
    """Revision-aware research raw candidate 隔離建置器。"""

    def __init__(self, request: RevisionAwareRawRequest) -> None:
        self.request = request
        self._request_output_owned = False
        self._verified_source_context: Any | None = None
        self.decision_utc = _parse_decision_at(request.decision_at)
        self.decision_taipei = self.decision_utc.astimezone(TAIPEI_TZ)
        self.history_start = date.fromisoformat(request.history_start_date)
        if self.history_start > self.decision_taipei.date():
            raise RevisionAwareCandidateError(
                f"history_start_date ({self.history_start}) exceeds decision_at ({self.decision_taipei.date()})"
            )
        provided_now = request.now_provider() if request.now_provider else _now_utc()
        self.now = _aware_utc(provided_now, "now_provider result")

    def build(self) -> RevisionAwareRawResult:
        self._request_output_owned = False
        try:
            return self._build_once()
        except Exception as exc:
            # 失敗收據只以 exclusive-create 寫入本次請求目錄；不覆寫舊產物。
            try:
                if not self._request_output_owned:
                    raise FileNotFoundError("this request did not create the output directory")
                failure_path = Path(self.request.output_dir) / "failure_receipt.json"
                failure_path.parent.mkdir(parents=True, exist_ok=True)
                with failure_path.open("xb") as stream:
                    stream.write(_canonical_json_bytes({
                        "schema_version": "ml-revision-aware-raw-failure.v1",
                        "status": "failed_closed",
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                        "recorded_at": _now_utc().isoformat(),
                        "research_only": True,
                        "formal_credit": False,
                    }))
            except (OSError, RevisionAwareCandidateError):
                pass
            raise

    def _build_once(self) -> RevisionAwareRawResult:
        req = self.request
        root = Path(__file__).resolve().parents[1]

        # 1. 隔離性與連結檢查
        _check_isolation(req.output_dir, "output_dir")
        _check_isolation(req.custody_dir, "custody_dir")
        _reject_links(req.snapshot_db, root, "snapshot_db")

        # 2. 事前來源不可變指紋採集
        db_fingerprint_before = _file_fingerprint(req.snapshot_db)
        if req.expected_snapshot_sha256:
            expected = req.expected_snapshot_sha256.lower()
            if not expected.startswith("sha256:"):
                expected = f"sha256:{expected}"
            actual = f"sha256:{db_fingerprint_before['sha256']}"
            if actual != expected:
                raise RevisionAwareCandidateError(
                    f"snapshot_db sha256 mismatch: actual={actual}, expected={expected}"
                )

        snapshot_context = self._verify_snapshot_context(db_fingerprint_before)
        self._snapshot_freeze_at = datetime.fromisoformat(snapshot_context["completed_at"])
        self._snapshot_sha256 = str(db_fingerprint_before["sha256"])
        self._snapshot_context_sha256 = str(snapshot_context["receipt_sha256"])
        if self._snapshot_freeze_at > self.decision_utc:
            raise RevisionAwareCandidateError(
                "snapshot current-observation freeze is after decision_at; use the actual current freeze as decision_at"
            )

        # 3. 來源 custody 清冊讀取與不可變指紋
        custody_fingerprints_before: list[dict[str, Any]] = []
        parsed_custody_rows: list[dict[str, Any]] = []
        for custody_manifest in req.source_custody_manifests:
            _reject_links(custody_manifest, root, "source_custody_manifest")
            fp = _file_fingerprint(custody_manifest)
            expected_hash = req.expected_source_manifest_hashes.get(str(custody_manifest))
            if expected_hash:
                exp_clean = expected_hash.lower()
                if not exp_clean.startswith("sha256:"):
                    exp_clean = f"sha256:{exp_clean}"
                if f"sha256:{fp['sha256']}" != exp_clean:
                    raise RevisionAwareCandidateError(
                        f"custody manifest hash mismatch: {custody_manifest}"
                    )
            custody_fingerprints_before.append(fp)
            # 解析 custody rows
            rows = self._load_custody_observations(custody_manifest)
            parsed_custody_rows.extend(rows)

        # 4. 評估 Market Revision Cutoff Policy
        revision_inspection = self._evaluate_market_revision()

        # 5. 預覽模式短路回傳
        if req.preview_only:
            return RevisionAwareRawResult(
                status="preview_only",
                manifest_path=req.output_dir / "manifest.json",
                manifest_hash="",
                manifest_file_sha256="",
                shards=(),
                row_count=len(parsed_custody_rows),
                feature_value_count=0,
                input_pins={
                    "snapshot_db": db_fingerprint_before,
                    "market_revision": revision_inspection,
                },
                safety=self._build_safety_block(),
            )

        # 6. 磁碟容量預檢
        self._check_disk_space(req.output_dir)

        # 7. 建立隔離輸出與保管目錄 (create-only 語意)
        self._prepare_output_directory(req.output_dir)
        self._prepare_output_directory(req.custody_dir)

        # 8. 抽取與建立 Shards
        shards_info, total_rows, total_values = self._export_shards(
            output_dir=req.output_dir,
            parsed_custody_rows=parsed_custody_rows,
        )

        # 9. 組合 Manifest
        code_identity = {
            "builder": _sha256_file(Path(__file__).resolve()),
            "cli": _sha256_file(root / "scripts" / "build_ml_revision_aware_raw_candidate.py")
            if (root / "scripts" / "build_ml_revision_aware_raw_candidate.py").exists()
            else "",
        }

        input_pins = {
            "snapshot_db": db_fingerprint_before,
            "snapshot_context": snapshot_context,
            "market_revision": revision_inspection,
            "source_custody": custody_fingerprints_before,
            "code_identity": code_identity,
        }

        safety_block = self._build_safety_block()

        manifest_payload: dict[str, Any] = {
            "schema_version": REVISION_AWARE_RAW_SCHEMA_VERSION,
            "stage": "research_raw_candidate",
            "dataset_id": f"ml-revision-aware-raw-{db_fingerprint_before['sha256'][:16]}",
            "decision_at": self.decision_utc.isoformat(),
            "decision_at_taipei": self.decision_taipei.isoformat(),
            "history_start_date": self.history_start.isoformat(),
            "created_at": self.now.isoformat(),
            "current_observation_freeze": {
                "available_at_or_before": snapshot_context["completed_at"],
                "identity": snapshot_context["receipt_sha256"],
            },
            "data_temporal_semantics": {
                "source_available_time_is_distinct_from_event_date": True,
                "current_restated": True,
                "historical_pit_eligible": False,
                "revision_custody_qualification": "verified_current_restated_research_context; historical PIT remains ineligible",
                "source_revision_qualification": snapshot_context["source_revision_qualification"],
            },
            "source_revision_qualification": snapshot_context["source_revision_qualification"],
            "format": "gzip_jsonl",
            "input_pins": input_pins,
            "safety": safety_block,
            "shard_count": len(shards_info),
            "row_count": total_rows,
            "feature_value_count": total_values,
            "observation_schema_version": "ml-revision-aware-observation.v1",
            "feature_registry": self._feature_registry(),
            "feature_registry_sha256": f"sha256:{_sha256_bytes(_canonical_json_bytes(self._feature_registry()))}",
            "shards": shards_info,
        }

        _assert_no_float(manifest_payload, "manifest_payload")

        # 計算 manifest hash (排除 manifest_hash 本身)
        manifest_hash = f"sha256:{_sha256_bytes(_canonical_json_bytes(manifest_payload))}"
        manifest_payload["manifest_hash"] = manifest_hash

        manifest_bytes = _canonical_json_bytes(manifest_payload)
        manifest_path = req.output_dir / "manifest.json"
        manifest_path.write_bytes(manifest_bytes)
        manifest_file_sha256 = f"sha256:{_sha256_bytes(manifest_bytes)}"

        # 10. 串流讀回驗證 (Readback Verification)
        self._verify_readback(manifest_path, manifest_bytes, shards_info)

        # 12. 事後來源不可變性核實 (Post-build Immutability Check)
        db_fingerprint_after = _file_fingerprint(req.snapshot_db)
        if db_fingerprint_before != db_fingerprint_after:
            raise RevisionAwareCandidateError(
                f"snapshot_db modified during build! before={db_fingerprint_before}, after={db_fingerprint_after}"
            )
        for fp_before in custody_fingerprints_before:
            fp_after = _file_fingerprint(Path(fp_before["path"]))
            if fp_before != fp_after:
                raise RevisionAwareCandidateError(
                    f"custody file modified during build: {fp_before['path']}"
                )

        # 11. 最後完成所有 bytes/readback/source immutability 驗證後才建立成功收據。
        receipt_payload = {
            "schema_version": REVISION_AWARE_COMPLETION_SCHEMA_VERSION,
            "status": "completed_research_only",
            "manifest_path": str(manifest_path.resolve()),
            "manifest_hash": manifest_hash,
            "manifest_file_sha256": manifest_file_sha256,
            "snapshot_context_receipt_sha256": snapshot_context["receipt_sha256"],
            "available_at_or_before": snapshot_context["completed_at"],
            "row_count": total_rows,
            "shard_count": len(shards_info),
            "verification_completed_at": _now_utc().isoformat(),
            "research_only": True,
            "formal_credit": False,
            "historical_pit_eligible": False,
            "direct_ooc_compatible": False,
            "source_revision_qualification": snapshot_context["source_revision_qualification"],
        }
        receipt_path = req.output_dir / "completion_receipt.json"
        with receipt_path.open("xb") as stream:
            stream.write(_canonical_json_bytes(receipt_payload))

        return RevisionAwareRawResult(
            status="completed_research_only",
            manifest_path=manifest_path,
            manifest_hash=manifest_hash,
            manifest_file_sha256=manifest_file_sha256,
            shards=tuple(shards_info),
            row_count=total_rows,
            feature_value_count=total_values,
            input_pins=input_pins,
            safety=safety_block,
            completion_receipt_path=receipt_path,
        )

    def _verify_snapshot_context(self, database_fingerprint: Mapping[str, Any]) -> dict[str, Any]:
        """驗證一致性快照收據並固定 current-observation freeze identity。"""
        receipt_path = self.request.snapshot_context_receipt_path
        expected = self.request.expected_snapshot_context_receipt_sha256
        if receipt_path is None or not expected:
            raise RevisionAwareCandidateError(
                "snapshot context receipt path and explicit SHA-256 pin are required"
            )
        _reject_links(receipt_path, Path(__file__).resolve().parents[1], "snapshot_context_receipt")
        receipt_bytes = receipt_path.read_bytes()
        actual_receipt_sha = f"sha256:{_sha256_bytes(receipt_bytes)}"
        expected_clean = expected.lower()
        if not expected_clean.startswith("sha256:"):
            expected_clean = f"sha256:{expected_clean}"
        if actual_receipt_sha != expected_clean:
            raise RevisionAwareCandidateError("snapshot context receipt SHA-256 mismatch")
        try:
            payload = json.loads(receipt_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RevisionAwareCandidateError("snapshot context receipt is not valid UTF-8 JSON") from exc
        snapshot = payload.get("snapshot")
        if (
            payload.get("schema_version") != "integration-consistent-sqlite-snapshot.v1"
            or payload.get("status") != "consistent_snapshot_created"
            or not isinstance(snapshot, dict)
            or payload.get("snapshot_quick_check") != "ok"
            or payload.get("source_and_revision_bytes_unchanged") is not True
        ):
            raise RevisionAwareCandidateError("snapshot context receipt does not prove a consistent snapshot")
        receipt_snapshot_path = Path(str(snapshot.get("path") or "")).resolve()
        if receipt_snapshot_path != self.request.snapshot_db.resolve():
            raise RevisionAwareCandidateError("snapshot context receipt is bound to a different SQLite file")
        db_sha = str(database_fingerprint.get("sha256") or "")
        if db_sha != str(snapshot.get("sha256") or "").removeprefix("sha256:"):
            raise RevisionAwareCandidateError("snapshot DB bytes do not match snapshot context receipt")
        snapshot_bytes = snapshot.get("bytes")
        snapshot_mtime_ns = snapshot.get("mtime_ns")
        if (
            isinstance(snapshot_bytes, bool)
            or not isinstance(snapshot_bytes, int)
            or snapshot_bytes != database_fingerprint.get("size_bytes")
            or isinstance(snapshot_mtime_ns, bool)
            or not isinstance(snapshot_mtime_ns, int)
            or snapshot_mtime_ns != database_fingerprint.get("mtime_ns")
        ):
            raise RevisionAwareCandidateError("snapshot DB bytes/mtime do not match snapshot context receipt")
        source_observation = payload.get("source_observation")
        if not isinstance(source_observation, dict):
            raise RevisionAwareCandidateError("snapshot context lacks original source observation pins")
        original_database = source_observation.get("database")
        original_wal = source_observation.get("wal")
        namespace_files = source_observation.get("revision_namespace_files")
        if not isinstance(original_database, dict) or not isinstance(original_wal, dict) or not isinstance(namespace_files, list):
            raise RevisionAwareCandidateError("snapshot original DB/revision namespace pin schema is invalid")
        if not isinstance(original_database.get("path"), str) or not original_database["path"]:
            raise RevisionAwareCandidateError("snapshot original source database path is missing")
        if str(payload.get("source_database_path") or "") != original_database["path"]:
            raise RevisionAwareCandidateError("snapshot original database path differs from source observation")
        for field_name in ("bytes", "mtime_ns"):
            field_value = original_database.get(field_name)
            if isinstance(field_value, bool) or not isinstance(field_value, int) or field_value < 0:
                raise RevisionAwareCandidateError(f"snapshot original database {field_name} pin is invalid")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", str(original_database.get("sha256") or "")):
            raise RevisionAwareCandidateError("snapshot original database SHA-256 pin is invalid")
        if not isinstance(original_wal.get("path"), str) or not original_wal["path"]:
            raise RevisionAwareCandidateError("snapshot original source WAL path is missing")
        for field_name in ("bytes", "mtime_ns"):
            field_value = original_wal.get(field_name)
            if isinstance(field_value, bool) or not isinstance(field_value, int) or field_value < 0:
                raise RevisionAwareCandidateError(f"snapshot original source WAL {field_name} pin is invalid")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", str(original_wal.get("sha256") or "")):
            raise RevisionAwareCandidateError("snapshot original source WAL SHA-256 pin is invalid")
        normalized_namespace_pins: list[dict[str, Any]] = []
        for index, item in enumerate(namespace_files):
            if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not item["path"]:
                raise RevisionAwareCandidateError(f"snapshot revision namespace pin {index} is invalid")
            for field_name in ("bytes", "mtime_ns"):
                field_value = item.get(field_name)
                if isinstance(field_value, bool) or not isinstance(field_value, int) or field_value < 0:
                    raise RevisionAwareCandidateError(f"snapshot revision namespace pin {index} {field_name} is invalid")
            if not re.fullmatch(r"[0-9a-fA-F]{64}", str(item.get("sha256") or "")):
                raise RevisionAwareCandidateError(f"snapshot revision namespace pin {index} SHA-256 is invalid")
            normalized_namespace_pins.append({
                "path": item["path"],
                "bytes": item["bytes"],
                "mtime_ns": item["mtime_ns"],
                "sha256": str(item["sha256"]).lower(),
            })
        # Integration receipt 將 generation pins 放在 root payload；不得從
        # source_observation 或 snapshot 子物件猜補。
        generation_before = payload.get("source_generation_before")
        generation_after = payload.get("source_generation_after")
        if (
            isinstance(generation_before, bool)
            or not isinstance(generation_before, int)
            or isinstance(generation_after, bool)
            or not isinstance(generation_after, int)
            or generation_before != generation_after
        ):
            raise RevisionAwareCandidateError("snapshot source generation pins are missing or inconsistent")
        completed_at = payload.get("completed_at")
        if not isinstance(completed_at, str):
            raise RevisionAwareCandidateError("snapshot context receipt is missing completed_at")
        try:
            completed_dt = datetime.fromisoformat(completed_at)
        except ValueError as exc:
            raise RevisionAwareCandidateError("snapshot completed_at is invalid") from exc
        completed_utc = _aware_utc(completed_dt, "snapshot completed_at")
        if completed_utc > self.now.astimezone(timezone.utc):
            raise RevisionAwareCandidateError("snapshot completed_at is after the current run freeze")
        try:
            verified_source_context = load_verified_current_restated_source_context(
                self.request.snapshot_db,
                receipt_path,
                expected_snapshot_database_sha256=f"sha256:{db_sha}",
                expected_snapshot_receipt_sha256=actual_receipt_sha,
                original_database_path=Path(original_database["path"]),
                decision_at=self.decision_utc,
                training_as_of=self.now,
            )
        except Exception as exc:
            raise RevisionAwareCandidateError(
                f"source_context_not_verified: {exc}"
            ) from exc
        self._verified_source_context = verified_source_context
        namespace_files_verified = [
            {
                "path": item.path,
                "bytes": item.bytes,
                "mtime_ns": item.mtime_ns,
                "sha256": item.sha256,
            }
            for item in verified_source_context.revision_namespace_files
        ]
        original_source_identity = {
            "database": {
                "path": verified_source_context.source_database_path,
                "bytes": original_database["bytes"],
                "mtime_ns": original_database["mtime_ns"],
                "sha256": verified_source_context.source_database_sha256,
            },
            "wal": {
                "path": verified_source_context.source_wal_path,
                "bytes": original_wal["bytes"],
                "mtime_ns": original_wal["mtime_ns"],
                "sha256": verified_source_context.source_wal_sha256,
            },
            "revision_namespace_files": namespace_files_verified,
            "source_generation": verified_source_context.source_generation,
            "revision_namespace_bundle_sha256": verified_source_context.revision_namespace_bundle_sha256,
            "source_revision_evidence_sha256": verified_source_context.source_revision_evidence_sha256,
            "source_revision_evidence_namespaces": list(verified_source_context.source_revision_evidence_namespaces),
            "source_observed_at": verified_source_context.source_observed_at.isoformat(),
            "current_restated": verified_source_context.current_restated,
            "historical_pit_eligible": verified_source_context.historical_pit_eligible,
        }
        return {
            "receipt_path": str(receipt_path.resolve()),
            "receipt_sha256": actual_receipt_sha,
            "completed_at": completed_utc.isoformat(),
            "snapshot_path": str(receipt_snapshot_path),
            "snapshot_sha256": f"sha256:{db_sha}",
            "source_database_path": payload.get("source_database_path"),
            "revision_custody_qualification": payload.get("revision_custody_qualification"),
            "source_revision_qualification": "verified_current_restated_source_context",
            "source_observed_at": verified_source_context.source_observed_at.isoformat(),
            "original_source_identity": original_source_identity,
            "verified_current_restated_source_context": {
                "source_database_sha256": verified_source_context.source_database_sha256,
                "source_wal_sha256": verified_source_context.source_wal_sha256,
                "snapshot_database_sha256": verified_source_context.snapshot_database_sha256,
                "snapshot_receipt_sha256": verified_source_context.snapshot_receipt_sha256,
                "decision_at": verified_source_context.decision_at.isoformat(),
                "training_as_of": verified_source_context.training_as_of.isoformat(),
                "source_observed_at": verified_source_context.source_observed_at.isoformat(),
                "source_generation": verified_source_context.source_generation,
                "revision_namespace_bundle_sha256": verified_source_context.revision_namespace_bundle_sha256,
                "source_revision_evidence_sha256": verified_source_context.source_revision_evidence_sha256,
                "source_revision_evidence_namespaces": list(verified_source_context.source_revision_evidence_namespaces),
                "current_restated": verified_source_context.current_restated,
                "historical_pit_eligible": verified_source_context.historical_pit_eligible,
            },
            "historical_pit_eligible": False,
        }

    def _build_safety_block(self) -> dict[str, Any]:
        return {
            "research_only": True,
            "candidate_only": True,
            "formal_dataset": False,
            "formal_credit": False,
            "formal_historical_PIT": False,
            "formal_oos": False,
            "promotion_eligible": False,
            "formal_source_contract_eligible": False,
            "unit_claimed": False,
            "direct_ooc_compatible": False,
            "market_revision_cutoff_policy_evaluated": True,
            "historical_pit_eligible": False,
            "data_semantics": "current_restated_observations_only",
            "no_naked_float_persistence": True,
        }

    @staticmethod
    def _feature_registry() -> list[dict[str, Any]]:
        return [
            {"feature_id": "daily_prices.開盤價", "scale": 2, "unit": "TWD/share", "value_type": "scaled_integer"},
            {"feature_id": "daily_prices.最高價", "scale": 2, "unit": "TWD/share", "value_type": "scaled_integer"},
            {"feature_id": "daily_prices.最低價", "scale": 2, "unit": "TWD/share", "value_type": "scaled_integer"},
            {"feature_id": "daily_prices.收盤價", "scale": 2, "unit": "TWD/share", "value_type": "scaled_integer"},
            {"feature_id": "daily_prices.成交股數", "scale": 0, "unit": "share", "value_type": "scaled_integer"},
            {"feature_id": "daily_prices.成交金額", "scale": 0, "unit": "TWD", "value_type": "scaled_integer"},
            {"feature_id": "daily_prices.成交筆數", "scale": 0, "unit": "trade", "value_type": "scaled_integer"},
        ]

    def _check_disk_space(self, target_dir: Path) -> None:
        parent = target_dir.parent
        while not parent.exists() and parent != parent.parent:
            parent = parent.parent
        free_bytes = shutil.disk_usage(parent).free
        if free_bytes < MIN_FREE_BYTES:
            raise RevisionAwareCandidateError(
                f"insufficient free disk space: {free_bytes} < {MIN_FREE_BYTES}"
            )

    def _prepare_output_directory(self, target_dir: Path) -> None:
        if target_dir.exists():
            raise RevisionAwareCandidateError(
                f"output directory already exists; retry with a new request-owned path: {target_dir}"
            )
        else:
            target_dir.mkdir(parents=True, exist_ok=False)
            if target_dir == self.request.output_dir:
                self._request_output_owned = True

    def _evaluate_market_revision(self) -> dict[str, Any]:
        """摘要已驗證原始四 namespace；研究仍不得升格為歷史 PIT。"""
        context = self._verified_source_context
        if context is None:
            # 不能把 snapshot copy 的空 namespaces 當成 clean evidence。
            raise RevisionAwareCandidateError("source_context_not_verified: strict source context is absent")
        return {
            "presence": "verified_current_restated",
            "cutoff_evaluated": True,
            "blocks_historical_pit": True,
            "source_revision_qualification": "verified_current_restated_source_context",
            "source_revision_evidence_sha256": context.source_revision_evidence_sha256,
            "revision_namespace_bundle_sha256": context.revision_namespace_bundle_sha256,
            "revision_namespace_count": len(context.revision_namespace_files),
            "source_revision_evidence_namespaces": list(context.source_revision_evidence_namespaces),
            "source_observed_at": context.source_observed_at.isoformat(),
            "requested_market_revision_receipts_dir": (
                str(self.request.market_revision_receipts_dir.resolve())
                if self.request.market_revision_receipts_dir
                else None
            ),
        }

    def _load_custody_observations(self, manifest_path: Path) -> list[dict[str, Any]]:
        """讀取前瞻日捕獲或每日來源列投影中的觀察值。"""
        expected_hash = self.request.expected_source_manifest_hashes.get(
            str(manifest_path.resolve())
        )
        if not expected_hash:
            raise RevisionAwareCandidateError(
                f"source manifest requires an explicit expected bytes SHA-256 pin: {manifest_path}"
            )
        manifest_raw = manifest_path.read_bytes()
        actual_manifest_sha = f"sha256:{_sha256_bytes(manifest_raw)}"
        expected_clean = expected_hash.lower()
        if not expected_clean.startswith("sha256:"):
            expected_clean = f"sha256:{expected_clean}"
        if actual_manifest_sha != expected_clean:
            raise RevisionAwareCandidateError("source custody manifest bytes SHA-256 mismatch")
        manifest = json.loads(manifest_raw.decode("utf-8"))
        schema = str(manifest.get("schema_version") or "")

        rows: list[dict[str, Any]] = []

        if schema == "ml-daily-source-row-research-projection.v1":
            # 每日來源列投影：以實際 bytes、canonical hash、terminal receipt 及來源輸入 pins 驗證。
            content_body = dict(manifest)
            declared_content_sha = content_body.pop("content_sha256", None)
            actual_content_sha = f"sha256:{_sha256_bytes(_canonical_json_bytes(content_body))}"
            if declared_content_sha != actual_content_sha:
                raise RevisionAwareCandidateError("projection canonical content hash mismatch")
            obs_file_info = manifest.get("observations_file")
            obs_filename_val: Any = None
            if isinstance(obs_file_info, dict):
                obs_filename_val = obs_file_info.get("path")
            if not obs_filename_val:
                obs_filename_val = manifest.get("observations_path") or "observations.jsonl"
            obs_file = manifest_path.parent / str(obs_filename_val)
            _reject_links(obs_file, Path(__file__).resolve().parents[1], "projection observations")
            if not obs_file.exists():
                raise RevisionAwareCandidateError(f"observations file not found: {obs_file}")
            expected_obs_sha = (
                obs_file_info.get("sha256")
                if isinstance(obs_file_info, dict)
                else manifest.get("observations_sha256")
            )
            if expected_obs_sha and expected_obs_sha.lower().startswith("sha256:"):
                expected_clean = expected_obs_sha.lower()[7:]
            else:
                expected_clean = (expected_obs_sha or "").lower()
            actual_obs_sha = _sha256_file(obs_file)
            if not expected_clean or actual_obs_sha.lower() != expected_clean:
                raise RevisionAwareCandidateError(
                    f"observations sha256 mismatch in custody: {obs_file}"
                )
            if isinstance(obs_file_info, dict):
                if obs_file.stat().st_size != _strict_int(obs_file_info.get("bytes"), "observations_file.bytes"):
                    raise RevisionAwareCandidateError("observations bytes length mismatch")
            declared_rows = obs_file_info.get("row_count") if isinstance(obs_file_info, dict) else None
            if isinstance(declared_rows, bool) or not isinstance(declared_rows, int) or declared_rows < 1:
                raise RevisionAwareCandidateError("projection observations row_count must be a positive integer")

            # 驗證 projection 的所有複製輸入 bytes，並要求 terminal receipt 完整綁定同一 manifest。
            input_files = manifest.get("input_files")
            if not isinstance(input_files, dict) or not input_files:
                raise RevisionAwareCandidateError("projection input_files pins are missing")
            verified_input_hashes: set[str] = set()
            for rel_name, pin in input_files.items():
                if not isinstance(rel_name, str) or not isinstance(pin, dict):
                    raise RevisionAwareCandidateError("projection input_files schema is invalid")
                input_path = (manifest_path.parent / rel_name).resolve()
                if not input_path.is_relative_to(manifest_path.parent.resolve()):
                    raise RevisionAwareCandidateError("projection input path escapes its root")
                _reject_links(input_path, Path(__file__).resolve().parents[1], "projection input")
                if not input_path.is_file() or _sha256_file(input_path) != str(pin.get("sha256", "")).removeprefix("sha256:"):
                    raise RevisionAwareCandidateError(f"projection input bytes pin mismatch: {rel_name}")
                if input_path.stat().st_size != _strict_int(pin.get("bytes"), f"input_files.{rel_name}.bytes"):
                    raise RevisionAwareCandidateError(f"projection input bytes length mismatch: {rel_name}")
                verified_input_hashes.add(str(pin.get("sha256")))
            completion_path = manifest_path.parent / "completion_receipt.json"
            terminal_path = manifest_path.parent / "runner_terminal_verification_receipt.json"
            if not completion_path.is_file() or not terminal_path.is_file():
                raise RevisionAwareCandidateError("projection lacks completion and terminal verification receipts")
            completion = json.loads(completion_path.read_text(encoding="utf-8"))
            terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
            if (
                completion.get("schema_version") != "ml-daily-source-row-research-completion.v1"
                or completion.get("completion_status") != "awaiting_terminal_revision_validation"
                or completion.get("manifest_sha256") != actual_manifest_sha
                or completion.get("observations_sha256") != f"sha256:{actual_obs_sha}"
            ):
                raise RevisionAwareCandidateError("projection completion receipt binding is invalid")
            projection_terminal = terminal.get("projection")
            if (
                terminal.get("schema_version") != "ml-daily-source-row-runner-terminal-receipt.v1"
                or terminal.get("terminal_status") != "completed_research_only"
                or not isinstance(projection_terminal, dict)
                or projection_terminal.get("manifest_sha256") != actual_manifest_sha
                or projection_terminal.get("observations_sha256") != f"sha256:{actual_obs_sha}"
                or terminal.get("features_included") is not False
                or terminal.get("labels_included") is not False
            ):
                raise RevisionAwareCandidateError("projection terminal verification receipt is invalid")
            with obs_file.open("r", encoding="utf-8") as stream:
                observed_rows = 0
                for line_idx, line in enumerate(stream, start=1):
                    line = line.strip()
                    if not line:
                        raise RevisionAwareCandidateError(f"blank projection observation line: {line_idx}")
                    item = json.loads(line)
                    observed_rows += 1
                    avail_str = item.get("source_available_at")
                    if not avail_str:
                        raise RevisionAwareCandidateError(f"custody row missing source_available_at at line {line_idx}")
                    try:
                        avail_dt = datetime.fromisoformat(avail_str)
                    except (TypeError, ValueError) as exc:
                        raise RevisionAwareCandidateError("source_available_at is invalid") from exc
                    avail_dt = _aware_utc(avail_dt, "source_available_at")
                    if avail_dt > self.decision_utc:
                        raise RevisionAwareCandidateError(
                            f"Lookahead violation in custody row: avail={avail_dt} > decision={self.decision_utc}"
                        )
                    source_date = _normalize_source_date(item.get("source_date"), "source_date")
                    symbol = item.get("symbol")
                    if not isinstance(symbol, str) or not _SYMBOL_PATTERN.fullmatch(symbol):
                        raise RevisionAwareCandidateError(f"invalid projection symbol at line {line_idx}")
                    exact_values = item.get("exact_numeric_values")
                    if not isinstance(exact_values, dict):
                        raise RevisionAwareCandidateError("exact_numeric_values must be an object")
                    standard_values: dict[str, dict[str, Any]] = {}
                    for name, value_record in exact_values.items():
                        if not isinstance(value_record, dict):
                            raise RevisionAwareCandidateError(f"numeric projection field {name} is invalid")
                        raw_int = _strict_int(value_record.get("value_int"), f"{name}.value_int")
                        raw_denominator = _strict_int(value_record.get("scale"), f"{name}.scale")
                        if raw_denominator < 1 or raw_denominator > 1_000_000:
                            raise RevisionAwareCandidateError(f"{name}.scale denominator is out of range")
                        exponent = 0
                        denom = raw_denominator
                        while denom > 1 and denom % 10 == 0:
                            exponent += 1
                            denom //= 10
                        if denom != 1 or exponent > 12:
                            raise RevisionAwareCandidateError(f"{name}.scale is not a bounded power of ten")
                        standard_values[name] = {
                            "value_int": raw_int,
                            "scale": exponent,
                            "source_scale_denominator": raw_denominator,
                            "unit": value_record.get("unit"),
                        }
                    source_pins = {
                        "raw_response_sha256": item.get("source_raw_response_sha256"),
                        "source_receipt_sha256": item.get("source_receipt_sha256"),
                        "source_row_index": _strict_int(item.get("source_row_index"), "source_row_index"),
                    }
                    if not all(isinstance(v, str) and v.startswith("sha256:") for k, v in source_pins.items() if k.endswith("sha256")):
                        raise RevisionAwareCandidateError("projection source provenance pins are incomplete")
                    if (
                        source_pins["raw_response_sha256"] not in verified_input_hashes
                        or source_pins["source_receipt_sha256"] not in verified_input_hashes
                    ):
                        raise RevisionAwareCandidateError("observation source pins do not match verified copied inputs")
                    rows.append({
                        "source": "daily_source_row_projection",
                        "symbol": symbol,
                        "date": source_date.isoformat(),
                        "event_date": source_date.isoformat(),
                        "available_at": avail_dt.isoformat(),
                        "exact_numeric_values": standard_values,
                        "source_provenance": source_pins,
                        "current_restated": True,
                        "source_values": item.get("source_values", {}),
                    })
                if observed_rows != declared_rows:
                    raise RevisionAwareCandidateError(
                        f"projection row count mismatch: actual={observed_rows}, declared={declared_rows}"
                    )
        elif schema == "ml-prospective-daily-price-candidate.v1":
            # 目前 prospective capture 尚無經驗證的標準 row adapter；明確回報 unsupported。
            raise RevisionAwareCandidateError(
                "prospective capture schema is typed unsupported until verified numeric rows are implemented"
            )
        else:
            raise RevisionAwareCandidateError(f"unsupported custody schema: {schema}")
        return rows

    def _export_shards(
        self,
        output_dir: Path,
        parsed_custody_rows: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], int, int]:
        """以單一 consistent read transaction 串流寫入 strict typed 年度 shards。"""
        shards_dir = output_dir / "shards"
        shards_dir.mkdir(parents=True, exist_ok=True)
        custody_by_year: dict[int, list[dict[str, Any]]] = {}
        for row in parsed_custody_rows:
            row_date = _normalize_source_date(row.get("date"), "custody date")
            if not self.request.years or row_date.year in self.request.years:
                custody_by_year.setdefault(row_date.year, []).append(row)

        start_iso = self.history_start.isoformat()
        end_iso = self.decision_taipei.date().isoformat()
        normalized_date_sql = (
            "CASE WHEN length(trim(CAST(日期 AS TEXT))) = 8 "
            "THEN substr(trim(CAST(日期 AS TEXT)),1,4)||'-'||substr(trim(CAST(日期 AS TEXT)),5,2)||'-'||substr(trim(CAST(日期 AS TEXT)),7,2) "
            "ELSE substr(trim(CAST(日期 AS TEXT)),1,10) END"
        )
        db_uri = f"file:{self.request.snapshot_db.resolve().as_posix()}?mode=ro"
        conn = sqlite3.connect(db_uri, uri=True)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            has_daily = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='daily_prices'"
            ).fetchone() is not None
            years_to_export = set(self.request.years or ())
            if has_daily and not years_to_export:
                years_sql = (
                    f"SELECT DISTINCT substr({normalized_date_sql},1,4) AS y "
                    f"FROM daily_prices WHERE {normalized_date_sql} >= ? AND {normalized_date_sql} <= ?"
                )
                for year_row in conn.execute(years_sql, (start_iso, end_iso)):
                    raw_year = year_row["y"]
                    if isinstance(raw_year, str) and re.fullmatch(r"\d{4}", raw_year):
                        years_to_export.add(int(raw_year))
            years_to_export.update(custody_by_year)
            if not years_to_export:
                years_to_export.add(self.decision_taipei.year)

            feature_specs = (
                ("daily_prices.開盤價", "開盤價", 2, "TWD/share"),
                ("daily_prices.最高價", "最高價", 2, "TWD/share"),
                ("daily_prices.最低價", "最低價", 2, "TWD/share"),
                ("daily_prices.收盤價", "收盤價", 2, "TWD/share"),
                ("daily_prices.成交股數", "成交股數", 0, "share"),
                ("daily_prices.成交金額", "成交金額", 0, "TWD"),
                ("daily_prices.成交筆數", "成交筆數", 0, "trade"),
            )
            shards_info: list[dict[str, Any]] = []
            total_rows = total_values = 0
            symbol_list = tuple(self.request.symbols or ())

            for year in sorted(years_to_export):
                rel_path = f"shards/{year}/observations.jsonl.gz"
                shard_path = output_dir / rel_path
                shard_path.parent.mkdir(parents=True, exist_ok=True)
                low = max(f"{year:04d}-01-01", start_iso)
                high = min(f"{year:04d}-12-31", end_iso)
                digest = hashlib.sha256()
                row_count = value_count = 0
                min_available: str | None = None
                max_available: str | None = None

                with shard_path.open("wb") as raw_stream:
                    with gzip.GzipFile(filename="", mode="wb", compresslevel=6, fileobj=raw_stream, mtime=0) as gz_stream:
                        if has_daily and low <= high:
                            where = f"{normalized_date_sql} >= ? AND {normalized_date_sql} <= ?"
                            params: list[Any] = [low, high]
                            if symbol_list:
                                placeholders = ",".join("?" for _ in symbol_list)
                                where += f" AND 證券代號 IN ({placeholders})"
                                params.extend(symbol_list)
                            query = (
                                "SELECT 證券代號, 日期, 開盤價, 最高價, 最低價, 收盤價, 成交股數, 成交金額, 成交筆數 "
                                f"FROM daily_prices WHERE {where} ORDER BY {normalized_date_sql}, 證券代號"
                            )
                            for db_row in conn.execute(query, params):
                                raw_symbol = db_row["證券代號"]
                                if not isinstance(raw_symbol, str):
                                    raise RevisionAwareCandidateError("SQLite symbol must remain text to preserve leading zeroes")
                                symbol = raw_symbol.strip()
                                if not symbol or len(symbol) > 16:
                                    raise RevisionAwareCandidateError("SQLite symbol is empty or too long")
                                row_date = _normalize_source_date(db_row["日期"], "SQLite 日期")
                                if row_date < self.history_start or row_date > self.decision_taipei.date():
                                    raise RevisionAwareCandidateError("SQLite query returned a date outside the bounded range")
                                values: list[dict[str, Any]] = []
                                missing: list[str] = []
                                quality_blocked: list[str] = []
                                staleness: list[str] = []
                                for feature_id, column, exponent, unit in feature_specs:
                                    raw_value = db_row[column]
                                    if raw_value is None:
                                        missing.append(feature_id)
                                        continue
                                    value_int = _strict_numeric_integer(raw_value, exponent, f"daily_prices.{column}")
                                    values.append({
                                        "feature_id": feature_id,
                                        "value_int": value_int,
                                        "scale": exponent,
                                        "status": "observed",
                                        "unit": unit,
                                        "source_scale_denominator": 10 ** exponent,
                                    })
                                if not values:
                                    raise RevisionAwareCandidateError("SQLite daily row has no numeric feature values")
                                avail_iso = self._snapshot_freeze_at.isoformat()
                                identity_fields = {
                                    "snapshot_sha256": self._snapshot_sha256,
                                    "symbol": symbol,
                                    "event_date": row_date.isoformat(),
                                    "values": values,
                                }
                                record: dict[str, Any] = {
                                    "schema_version": "ml-revision-aware-observation.v1",
                                    "entity_id": symbol,
                                    "symbol": symbol,
                                    "table_name": "daily_prices",
                                    "event_date": row_date.isoformat(),
                                    "event_at": row_date.isoformat(),
                                    "available_at": avail_iso,
                                    "source_available_at": avail_iso,
                                    "source_version": {
                                        "provider": "verified_sqlite_snapshot",
                                        "snapshot_sha256": self._snapshot_sha256,
                                        "context_receipt_sha256": self._snapshot_context_sha256,
                                    },
                                    "current_restated": True,
                                    "historical_pit_eligible": False,
                                    "values": values,
                                    "missing_mask": missing,
                                    "quality_blocked_mask": quality_blocked,
                                    "staleness_mask": staleness,
                                    "source_projection_row_identity_hash": f"sha256:{_sha256_bytes(_canonical_json_bytes(identity_fields))}",
                                }
                                _assert_no_float(record, "sqlite_record")
                                encoded = _canonical_json_bytes(record) + b"\n"
                                gz_stream.write(encoded)
                                digest.update(encoded)
                                row_count += 1
                                value_count += len(values)
                                min_available = avail_iso if min_available is None else min(min_available, avail_iso)
                                max_available = avail_iso if max_available is None else max(max_available, avail_iso)

                        for custody_row in custody_by_year.get(year, []):
                            symbol = custody_row["symbol"]
                            if symbol_list and symbol not in symbol_list:
                                continue
                            value_map = custody_row["exact_numeric_values"]
                            field_map = {
                                "開盤價": ("daily_prices.開盤價", 2, "TWD/share"),
                                "最高價": ("daily_prices.最高價", 2, "TWD/share"),
                                "最低價": ("daily_prices.最低價", 2, "TWD/share"),
                                "收盤價": ("daily_prices.收盤價", 2, "TWD/share"),
                                "成交股數": ("daily_prices.成交股數", 0, "share"),
                            }
                            values = []
                            missing = []
                            for key, (feature_id, exponent, unit) in field_map.items():
                                item = value_map.get(key)
                                if item is None:
                                    missing.append(feature_id)
                                    continue
                                source_exponent = _strict_int(item.get("scale"), f"{key}.scale")
                                value_int = _strict_int(item.get("value_int"), f"{key}.value_int")
                                if source_exponent != exponent:
                                    # 原始 denominator 只在 custody parser normalization 後轉為標準 exponent。
                                    denominator = source_exponent
                                    converted_exponent = 0
                                    while denominator > 1 and denominator % 10 == 0:
                                        denominator //= 10
                                        converted_exponent += 1
                                    if denominator != 1 or converted_exponent != exponent:
                                        raise RevisionAwareCandidateError(f"{key} has noncanonical standard exponent")
                                values.append({
                                    "feature_id": feature_id,
                                    "value_int": value_int,
                                    "scale": exponent,
                                    "status": "observed",
                                    "unit": unit,
                                    "source_scale_denominator": item.get("source_scale_denominator"),
                                })
                            if not values:
                                raise RevisionAwareCandidateError("custody projection row has no numeric features")
                            event_date = custody_row["event_date"]
                            avail_iso = custody_row["available_at"]
                            source_provenance = custody_row["source_provenance"]
                            identity_fields = {
                                "source_provenance": source_provenance,
                                "symbol": symbol,
                                "event_date": event_date,
                                "values": values,
                            }
                            record = {
                                "schema_version": "ml-revision-aware-observation.v1",
                                "entity_id": symbol,
                                "symbol": symbol,
                                "table_name": "daily_prices",
                                "event_date": event_date,
                                "event_at": event_date,
                                "available_at": avail_iso,
                                "source_available_at": avail_iso,
                                "source_version": {
                                    "provider": "daily_source_row_projection",
                                    "raw_response_sha256": source_provenance["raw_response_sha256"],
                                    "source_receipt_sha256": source_provenance["source_receipt_sha256"],
                                    "source_row_index": source_provenance["source_row_index"],
                                },
                                "current_restated": True,
                                "historical_pit_eligible": False,
                                "values": values,
                                "missing_mask": missing,
                                "quality_blocked_mask": [],
                                "staleness_mask": [],
                                "source_projection_row_identity_hash": f"sha256:{_sha256_bytes(_canonical_json_bytes(identity_fields))}",
                            }
                            _assert_no_float(record, "custody_record")
                            encoded = _canonical_json_bytes(record) + b"\n"
                            gz_stream.write(encoded)
                            digest.update(encoded)
                            row_count += 1
                            value_count += len(values)
                            min_available = avail_iso if min_available is None else min(min_available, avail_iso)
                            max_available = avail_iso if max_available is None else max(max_available, avail_iso)

                compressed_hash = _sha256_file(shard_path)
                uncompressed_hash = digest.hexdigest()
                shards_info.append({
                    "year": year,
                    "path": rel_path,
                    "compressed_sha256": f"sha256:{compressed_hash}",
                    "uncompressed_sha256": f"sha256:{uncompressed_hash}",
                    "file_sha256": f"sha256:{compressed_hash}",
                    "observations_sha256": f"sha256:{uncompressed_hash}",
                    "row_count": row_count,
                    "feature_value_count": value_count,
                    "min_available_at": min_available,
                    "max_available_at": max_available,
                    "row_schema": "ml-revision-aware-observation.v1",
                })
                total_rows += row_count
                total_values += value_count
            return shards_info, total_rows, total_values
        finally:
            conn.close()

    def _verify_readback(
        self,
        manifest_path: Path,
        manifest_bytes: bytes,
        shards_info: list[dict[str, Any]],
    ) -> None:
        """串流讀回校驗輸出內容。"""
        # 1. 讀回 manifest
        actual_manifest_bytes = manifest_path.read_bytes()
        if actual_manifest_bytes != manifest_bytes:
            raise RevisionAwareCandidateError("manifest readback mismatch")

        # 2. 逐 shard 讀回
        base_dir = manifest_path.parent
        for shard in shards_info:
            shard_path = base_dir / shard["path"]
            if not shard_path.exists():
                raise RevisionAwareCandidateError(f"shard file missing on readback: {shard_path}")
            # 核對 file_sha256
            actual_file_sha = f"sha256:{_sha256_file(shard_path)}"
            if actual_file_sha != shard["file_sha256"]:
                raise RevisionAwareCandidateError(
                    f"shard file sha256 mismatch on readback: {shard_path}"
                )
            # 解壓縮核對 observations_sha256 與 row_count
            obs_hasher = hashlib.sha256()
            read_rows = 0
            with gzip.open(shard_path, "rb") as gz:
                while line := gz.readline():
                    obs_hasher.update(line)
                    try:
                        row = json.loads(line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raise RevisionAwareCandidateError("shard row is not valid UTF-8 JSON") from exc
                    if row.get("schema_version") != "ml-revision-aware-observation.v1":
                        raise RevisionAwareCandidateError("shard row schema version mismatch")
                    if not isinstance(row.get("event_date"), str) or not isinstance(row.get("available_at"), str):
                        raise RevisionAwareCandidateError("shard row is missing typed event/availability dates")
                    try:
                        available = datetime.fromisoformat(row["available_at"])
                    except ValueError as exc:
                        raise RevisionAwareCandidateError("shard row available_at is invalid") from exc
                    _aware_utc(available, "shard available_at")
                    vals = row.get("values")
                    if not isinstance(vals, list):
                        raise RevisionAwareCandidateError("shard row values must be a list")
                    for value in vals:
                        if not isinstance(value, dict):
                            raise RevisionAwareCandidateError("shard feature value has invalid shape")
                        _strict_int(value.get("value_int"), "shard value_int")
                        scale = _strict_int(value.get("scale"), "shard scale")
                        if scale < 0 or scale > 12:
                            raise RevisionAwareCandidateError("shard scale is out of range")
                    read_rows += 1
            actual_obs_sha = f"sha256:{obs_hasher.hexdigest()}"
            if actual_obs_sha != shard["observations_sha256"]:
                raise RevisionAwareCandidateError(
                    f"shard observations sha256 mismatch on readback: {shard_path}"
                )
            if read_rows != shard["row_count"]:
                raise RevisionAwareCandidateError(
                    f"shard row count mismatch on readback: expected {shard['row_count']}, got {read_rows}"
                )
