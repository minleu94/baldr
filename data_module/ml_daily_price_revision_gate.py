"""歷史日價格來源修訂的 fail-closed guard。

修復工具在變更 SQLite 前寫入 pending marker，交易完成後再寫入 final
receipt。PIT/export 與唯讀歷史 snapshot 會從資料庫資料根目錄自動尋找
sidecar，caller 省略選配 CSV 參數也不能繞過 hold。本模組只讀 JSON metadata，
不開啟資料庫，也不載入模型 artifact。
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from data_module.contracts.source_revision import (
    SOURCE_REVISION_EVIDENCE_SCHEMA_V1,
    SourceEvidenceNamespaceV1,
    SourceEvidencePresenceV1,
    ValidatedEvidenceFileV1,
    ValidatedNamespaceEvidenceV1,
    ValidatedSourceEvidenceV1,
)


REPAIR_SCHEMA = "historical-price-spike-repair-20260921.v1"
REPAIR_RECEIPT_RELATIVE_DIR = Path(
    "output",
    "scheduled",
    "daily_price_repair_receipts",
    "20260520",
    "historical_price_spike_20260921",
)

# 先前訓練的 derived h5 release 之事故專用 immutable identity。release 仍保留
# 作為證據與重現用途，但來源包含 2026-05-20 修訂前的 daily_prices.ohlc；
# loader 必須標示 stale，並在 artifact 反序列化前停止。
KNOWN_MODEL_SOURCE_REVISION_QUARANTINES: dict[str, dict[str, str]] = {
    "sha256:5c851d94b4a9385b30317b345ff084cdc47cdc165394e5463061272fbad67a52": {
        "source_date": "2026-05-20",
        "identity": "repo:v4_ml_derived_h5_20260907_real/release_manifest.json",
        "release_manifest_hash": "sha256:b24e222352106fa91b389410e501a2c5589227eb792ba395463e5c948416482b",
        "status": "stale_source_revision",
    },
    "sha256:aa152ebb8e8d7913a6a2274a0526620d8b8ce151a5f667d8de446df9724c895c": {
        "source_date": "2026-05-20",
        "identity": "repo:v4_ml_derived_h5_20260907_real_v2/release_manifest.json",
        "release_manifest_hash": "sha256:c306c1ea53ccef112204a8412a605b575e4d107b4503b2b5be5d6d5ee50910ea",
        "status": "stale_source_revision",
    },
    "sha256:92668aa574967990fa560aef8a48e595296eb22f3fef2a4264cff08210d78b6d": {
        "source_date": "2026-05-20",
        "identity": "FA_Data/output/release_v4/ml_allocation_bounded_v4_operational/training_manifest_v2.json",
        "status": "stale_source_revision",
    },
}


class DailyPriceSourceRevisionError(ValueError):
    """來源修訂命中 PIT cutoff，舊資料流程必須停止。"""


class CurrentRestatedContractNotConnectedError(DailyPriceSourceRevisionError):
    """目前修訂值尚無獨立 current-restated consumer，不可進入 PIT rows。"""

    classification = "current_restated_contract_not_connected"


@dataclass(frozen=True, slots=True)
class VerifiedRevisionNamespaceFileV1:
    """一致性快照 receipt 所釘選的原始修訂 namespace 檔案。"""

    path: str
    bytes: int
    mtime_ns: int
    sha256: str


@dataclass(frozen=True, slots=True)
class VerifiedRevisionDependencyV1:
    """嚴格 revision validator 同次讀取的實體 dependency pin。"""

    namespace: str
    role_id: str
    path: str
    bytes: int
    mtime_ns: int
    sha256: str
    captured_at: datetime


@dataclass(frozen=True, slots=True)
class _CapturedDailyRepairReceipt:
    """同次讀取的 daily repair JSON 與實體檔案 pin。"""

    path: Path
    payload: Mapping[str, Any]
    sha256: str
    bytes: int
    mtime_ns: int


@dataclass(frozen=True, slots=True)
class VerifiedCurrentRestatedSourceContext:
    """綁定原始 DB、snapshot、namespace 與研究 custody 時計。"""

    source_database_path: str
    source_database_sha256: str
    source_wal_path: str
    source_wal_sha256: str
    snapshot_database_path: str
    snapshot_database_sha256: str
    snapshot_receipt_path: str
    snapshot_receipt_sha256: str
    decision_at: datetime
    training_as_of: datetime
    source_observed_at: datetime
    source_generation: int
    revision_namespace_files: tuple[VerifiedRevisionNamespaceFileV1, ...]
    revision_namespace_bundle_sha256: str
    source_revision_evidence_schema_version: str
    source_revision_evidence_scope_id: str
    source_revision_evidence_cutoff_date: str
    source_revision_evidence_sha256: str
    source_revision_evidence_namespaces: tuple[str, ...]
    source_revision_evidence_files: tuple[tuple[str, str, str], ...]
    revision_dependencies_verified_at: datetime
    revision_dependency_files: tuple[VerifiedRevisionDependencyV1, ...]
    revision_dependency_bundle_sha256: str
    current_restated: bool = True
    historical_pit_eligible: bool = False


def assert_model_artifact_source_revision_safe(artifact_hash: str) -> None:
    """在 wrapper 反序列化前拒絕已知的修復前 artifact。"""

    quarantine = KNOWN_MODEL_SOURCE_REVISION_QUARANTINES.get(str(artifact_hash))
    if quarantine is None:
        return
    raise DailyPriceSourceRevisionError(
        "model artifact is quarantined by a daily-price source revision; "
        f"artifact_hash={artifact_hash} source_date={quarantine['source_date']} "
        f"status={quarantine['status']} identity={quarantine['identity']} "
        f"{('release_manifest_hash=' + quarantine['release_manifest_hash'] + ' ') if quarantine.get('release_manifest_hash') else ''}"
        "rebuild and revalidate the model"
    )


def source_revision_receipt_candidates(
    *, database_path: Path,
    explicit_path: Path | None = None,
) -> tuple[Path, ...]:
    """找出既有 repair sidecar。

    ``database_path`` 通常位於 ``<data-root>/sqlite``；測試與隔離資料庫則
    可直接位於資料根目錄。正式路徑不需要 caller 另傳旗標，pending 與 final
    都會被檢查。
    """

    candidates, _, _, _ = _receipt_candidates_with_policy(
        database_path=database_path,
        explicit_path=explicit_path,
    )
    return candidates


def _receipt_candidates_with_policy(
    *,
    database_path: Path,
    explicit_path: Path | None,
    strict_explicit_slots: bool = False,
) -> tuple[tuple[Path, ...], frozenset[Path], Path, Mapping[Path, Path]]:
    database_root = database_path.resolve().parent
    if database_root.name.casefold() == "sqlite":
        database_root = database_root.parent
    database_root = database_root.resolve()
    automatic_pairs = _automatic_receipt_candidates(database_root)
    automatic = tuple(dict.fromkeys(path for path, _ in automatic_pairs))
    automatic_set = frozenset(automatic)
    automatic_sources = {
        path: source_path for path, source_path in automatic_pairs
    }
    if explicit_path is None:
        return automatic, automatic_set, database_root, automatic_sources
    _source_context_reject_reparse(
        explicit_path, "explicit daily-price repair receipt root"
    )
    explicit = explicit_path.resolve()
    explicit_paths = (
        (explicit / "pending.json", explicit / "receipt.json")
        if explicit.is_dir()
        else (explicit,)
    )
    if explicit.is_dir() and strict_explicit_slots:
        existing_explicit = tuple(
            resolved
            for path in explicit_paths
            if (resolved := _resolve_explicit_receipt_slot(path)) is not None
        )
    elif explicit.is_dir():
        # 舊 public gate 保留原有的 is_file() 篩選與 None 行為。
        existing_explicit = tuple(path for path in explicit_paths if path.is_file())
    else:
        existing_explicit = explicit_paths
    return (
        tuple(dict.fromkeys((*automatic, *existing_explicit))),
        automatic_set,
        database_root,
        automatic_sources,
    )


def _resolve_explicit_receipt_slot(path: Path) -> Path | None:
    """在 typed collection 中區分真正缺席與不完整的 explicit slot。"""

    try:
        path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise DailyPriceSourceRevisionError(
            f"explicit receipt slot is unreadable: {path}"
        ) from exc

    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise DailyPriceSourceRevisionError(
            f"explicit receipt slot is unresolved: {path}"
        ) from exc
    try:
        file_info = resolved.lstat()
    except OSError as exc:
        raise DailyPriceSourceRevisionError(
            f"explicit receipt slot is unreadable: {resolved}"
        ) from exc
    if not stat.S_ISREG(file_info.st_mode):
        raise DailyPriceSourceRevisionError(
            f"explicit receipt slot is not a regular file: {resolved}"
        )
    return resolved


def _automatic_receipt_candidates(database_root: Path) -> tuple[tuple[Path, Path], ...]:
    """逐段驗證固定自動搜尋路徑，只有普通缺席可代表無候選。"""

    try:
        root_info = database_root.lstat()
    except FileNotFoundError:
        return ()
    except OSError as exc:
        raise DailyPriceSourceRevisionError(
            f"automatic source revision receipt root is unreadable: {database_root}"
        ) from exc
    if not stat.S_ISDIR(root_info.st_mode):
        raise DailyPriceSourceRevisionError(
            f"automatic source revision receipt root is not a directory: {database_root}"
        )

    current = database_root
    lexical_current = database_root
    for component in REPAIR_RECEIPT_RELATIVE_DIR.parts:
        lexical_current = lexical_current / component
        try:
            lexical_current.lstat()
        except FileNotFoundError:
            return ()
        except OSError as exc:
            raise DailyPriceSourceRevisionError(
                f"automatic source revision receipt path is unreadable: {lexical_current}"
            ) from exc
        current = _resolve_automatic_receipt_path(
            lexical_current,
            database_root=database_root,
            require_file=False,
        )
        if not current.is_dir():
            raise DailyPriceSourceRevisionError(
                f"automatic source revision receipt path is not a directory: {current}"
            )

    candidates: list[tuple[Path, Path]] = []
    for filename in ("pending.json", "receipt.json"):
        child = lexical_current / filename
        try:
            child.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise DailyPriceSourceRevisionError(
                f"automatic source revision receipt is unreadable: {child}"
            ) from exc
        candidates.append((
            _resolve_automatic_receipt_path(
                child,
                database_root=database_root,
                require_file=True,
            ),
            child,
        ))
    return tuple(dict.fromkeys(candidates))


def _resolve_automatic_receipt_path(
    path: Path,
    *,
    database_root: Path,
    require_file: bool,
) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise DailyPriceSourceRevisionError(
            f"automatic source revision receipt path is unresolved: {path}"
        ) from exc
    try:
        resolved.relative_to(database_root)
    except ValueError as exc:
        raise DailyPriceSourceRevisionError(
            f"automatic source revision receipt path is outside data root: {path}"
        ) from exc
    if require_file:
        try:
            file_info = resolved.lstat()
        except OSError as exc:
            raise DailyPriceSourceRevisionError(
                f"automatic source revision receipt is unreadable: {resolved}"
            ) from exc
        if not stat.S_ISREG(file_info.st_mode):
            raise DailyPriceSourceRevisionError(
                f"automatic source revision receipt is not a regular file: {resolved}"
            )
    return resolved


def check_daily_price_source_revision(
    *,
    database_path: Path,
    decision_date: date | datetime | str,
    symbols: Iterable[str] | None = None,
    explicit_path: Path | None = None,
    allow_source_revision_research: bool = False,
) -> dict[str, Any] | None:
    """以決策 cutoff 檢查所有找到的 receipt。

    修復日是來源修訂日，不是新的歷史 ``available_at``。因此即使
    ``history_start_date`` 較晚，決策日到達修訂日仍會阻擋：rolling feature
    與較早 horizon label 可能依賴修正列。pending marker 代表 SQLite 交易
    可能已 commit 但 final receipt 尚未寫入，故視為 all-symbol hold。
    """

    cutoff = _as_date(decision_date)
    normalized_symbols = (
        None
        if symbols is None
        else frozenset(str(symbol).strip() for symbol in symbols if str(symbol).strip())
    )
    if normalized_symbols is not None and not normalized_symbols:
        raise ValueError("symbols must not be empty when supplied")

    # Preserve the established formal/PIT path. The richer immutable dependency
    # capture below is reserved for the explicitly opted-in current-restated
    # research context loader.
    if not allow_source_revision_research:
        from data_module.formal_market_revision import assert_market_revision_safe
        from data_module.historical_session_revision import assert_session_revision_safe
        from data_module.excluded_daily_price_revision import assert_excluded_source_revision_safe

        try:
            assert_market_revision_safe(database_path, cutoff)
            assert_session_revision_safe(database_path, cutoff)
            assert_excluded_source_revision_safe(database_path, cutoff)
        except ValueError as exc:
            raise DailyPriceSourceRevisionError(str(exc)) from exc
        legacy_summary, _evidence_files = _inspect_daily_price_repair_receipts_once(
            database_path=database_path,
            decision=cutoff,
            symbols=normalized_symbols,
            explicit_path=explicit_path,
            strict_explicit_slots=False,
        )
        return legacy_summary

    try:
        (
            evidence_bundle,
            revision_states,
            blocked_namespaces,
            daily_summary,
            revision_dependencies,
        ) = (
            _collect_validated_source_revision_bundle(
                database_path=database_path,
                cutoff=cutoff,
                symbols=normalized_symbols,
                explicit_path=explicit_path,
                allow_source_revision_research=allow_source_revision_research,
            )
        )
    except DailyPriceSourceRevisionError:
        raise
    except (OSError, RuntimeError, KeyError, TypeError, ValueError) as exc:
        raise DailyPriceSourceRevisionError(str(exc)) from exc
    if blocked_namespaces and not allow_source_revision_research:
        raise DailyPriceSourceRevisionError(
            "validated source revision blocks historical PIT; rebuild features/labels "
            "with a revision-aware research or formal process: "
            + ", ".join(blocked_namespaces)
        )

    if not evidence_bundle.namespaces or (
        not allow_source_revision_research
        and all(
            item.presence is SourceEvidencePresenceV1.EMPTY
            for item in evidence_bundle.namespaces
        )
    ):
        return None

    research_summary: dict[str, Any] = {
        "schema_version": REPAIR_SCHEMA,
        "checked_receipt_count": (
            0 if daily_summary is None else daily_summary["checked_receipt_count"]
        ),
        "checked_receipts": (
            [] if daily_summary is None else daily_summary["checked_receipts"]
        ),
        "relevant_row_count": (
            0 if daily_summary is None else daily_summary["relevant_row_count"]
        ),
        "policy": (
            "revision_aware_research"
            if blocked_namespaces
            else "fail_closed_until_repaired_source_rebuild"
        ),
        "database_path": str(Path(database_path).expanduser().resolve()),
        "decision_date": cutoff.isoformat(),
        "validated_revision_states": revision_states,
        "source_revision_evidence": _source_evidence_payload(evidence_bundle),
        "source_revision_evidence_sha256": evidence_bundle.digest_sha256,
        "validated_revision_dependencies": [
            {
                "namespace": item.namespace,
                "role_id": item.role_id,
                "path": item.path,
                "bytes": item.bytes,
                "mtime_ns": item.mtime_ns,
                "sha256": item.sha256,
                "captured_at": item.captured_at.isoformat(),
            }
            for item in revision_dependencies
        ],
        "current_restated_research": bool(blocked_namespaces),
        "market_revision_blocks_historical_pit": bool(blocked_namespaces),
    }
    research_summary["validated_revision_dependencies_sha256"] = (
        _source_context_canonical_sha256(
            research_summary["validated_revision_dependencies"]
        )
    )
    if blocked_namespaces:
        research_summary.update(
            {
                "research_only": True,
                "formal_historical_PIT": False,
                "formal_training_allowed": False,
                "formal_oos_allowed": False,
                "production_alpha_bp": 0,
                "revision_blocked_reasons": blocked_namespaces,
            }
        )
    return research_summary


def load_verified_current_restated_source_context(
    snapshot_database_path: Path,
    snapshot_receipt_path: Path,
    *,
    expected_snapshot_database_sha256: str,
    expected_snapshot_receipt_sha256: str,
    original_database_path: Path,
    decision_at: datetime | str,
    training_as_of: datetime | str,
) -> VerifiedCurrentRestatedSourceContext:
    """驗證原始 source DB、namespace dependency 與一致性 SQLite snapshot。

    ``decision_at`` 與 ``training_as_of`` 都必須是明確帶時區的時間；後者
    僅是 source selection cutoff，不代表模型實際訓練時點。revision gate 以
    decision_at 的台北日曆日檢查。SQLite source observation 只取 snapshot
    receipt 的 completed_at；外部 dependency 的驗證完成時鐘獨立保存，不回填
    成歷史公告或 source availability。
    """

    decision_utc = _source_context_aware_utc(decision_at, "decision_at")
    training_utc = _source_context_aware_utc(
        training_as_of, "training_as_of"
    )
    if decision_utc > training_utc:
        raise CurrentRestatedContractNotConnectedError(
            "decision_at cannot exceed training_as_of"
        )

    receipt_path = _source_context_regular_path(
        Path(snapshot_receipt_path), "snapshot receipt"
    )
    snapshot_path = _source_context_regular_path(
        Path(snapshot_database_path), "snapshot database"
    )
    source_path = _source_context_regular_path(
        Path(original_database_path), "original source database"
    )
    receipt_info_before = receipt_path.stat()
    receipt_bytes = receipt_path.read_bytes()
    receipt_info_after = receipt_path.stat()
    if (
        len(receipt_bytes) != receipt_info_before.st_size
        or receipt_info_before.st_size != receipt_info_after.st_size
        or receipt_info_before.st_mtime_ns != receipt_info_after.st_mtime_ns
        or receipt_path.resolve(strict=True) != receipt_path
    ):
        raise CurrentRestatedContractNotConnectedError(
            "snapshot receipt changed while being captured"
        )
    receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest()
    if receipt_sha256 != _source_context_pin(
        expected_snapshot_receipt_sha256, "expected_snapshot_receipt_sha256"
    ):
        raise CurrentRestatedContractNotConnectedError(
            "snapshot receipt actual-bytes SHA-256 mismatch"
        )
    try:
        receipt = json.loads(receipt_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CurrentRestatedContractNotConnectedError(
            "snapshot receipt is not valid UTF-8 JSON"
        ) from exc
    if not isinstance(receipt, dict):
        raise CurrentRestatedContractNotConnectedError(
            "snapshot receipt root must be an object"
        )
    if (
        receipt.get("schema_version")
        != "integration-consistent-sqlite-snapshot.v1"
        or receipt.get("status") != "consistent_snapshot_created"
        or receipt.get("consistency")
        != "sqlite_backup_from_single_query_only_read_transaction"
        or receipt.get("snapshot_quick_check") != "ok"
        or receipt.get("source_and_revision_bytes_unchanged") is not True
    ):
        raise CurrentRestatedContractNotConnectedError(
            "snapshot receipt does not prove a consistent immutable read"
        )

    source_observation = receipt.get("source_observation")
    if not isinstance(source_observation, dict):
        raise CurrentRestatedContractNotConnectedError(
            "snapshot receipt is missing source observation pins"
        )
    source_db = source_observation.get("database")
    source_wal = source_observation.get("wal")
    snapshot = receipt.get("snapshot")
    if not isinstance(source_db, dict) or not isinstance(source_wal, dict):
        raise CurrentRestatedContractNotConnectedError(
            "snapshot receipt is missing source database or WAL pins"
        )
    if not isinstance(snapshot, dict):
        raise CurrentRestatedContractNotConnectedError(
            "snapshot receipt is missing snapshot pins"
        )

    receipt_source_path = _source_context_receipt_path(
        source_db.get("path"), "source_observation.database.path"
    )
    receipt_top_source_path = _source_context_receipt_path(
        receipt.get("source_database_path"), "source_database_path"
    )
    if (
        not _source_context_same_path(receipt_source_path, source_path)
        or not _source_context_same_path(
            receipt_top_source_path, source_path
        )
    ):
        raise CurrentRestatedContractNotConnectedError(
            "snapshot receipt is not bound to the supplied original source database"
        )

    receipt_snapshot_path = _source_context_receipt_path(
        snapshot.get("path"), "snapshot.path"
    )
    if not _source_context_same_path(receipt_snapshot_path, snapshot_path):
        raise CurrentRestatedContractNotConnectedError(
            "snapshot receipt is bound to a different SQLite file"
        )

    generation_before = _source_context_nonnegative_int(
        receipt.get("source_generation_before"),
        "source_generation_before",
    )
    generation_after = _source_context_nonnegative_int(
        receipt.get("source_generation_after"), "source_generation_after"
    )
    if generation_before != generation_after:
        raise CurrentRestatedContractNotConnectedError(
            "source generation changed during snapshot"
        )

    source_db_sha256 = _source_context_check_file_pin(
        source_path,
        source_db,
        label="original source database",
    )
    source_wal_path = _source_context_regular_path(
        _source_context_receipt_path(source_wal.get("path"), "source_observation.wal.path"),
        "source WAL",
    )
    source_wal_sha256 = _source_context_check_file_pin(
        source_wal_path, source_wal, label="source WAL"
    )
    snapshot_sha256 = _source_context_check_file_pin(
        snapshot_path, snapshot, label="snapshot database"
    )
    if snapshot_sha256 != _source_context_pin(
        expected_snapshot_database_sha256,
        "expected_snapshot_database_sha256",
    ):
        raise CurrentRestatedContractNotConnectedError(
            "snapshot database actual-bytes SHA-256 mismatch"
        )

    completed_at = _source_context_aware_utc(
        receipt.get("completed_at"), "snapshot completed_at"
    )
    started_at = _source_context_aware_utc(
        receipt.get("started_at"), "snapshot started_at"
    )
    if completed_at < started_at:
        raise CurrentRestatedContractNotConnectedError(
            "snapshot completed_at precedes started_at"
        )
    if completed_at > decision_utc or completed_at > training_utc:
        raise CurrentRestatedContractNotConnectedError(
            "snapshot observed_at is after decision_at or training_as_of"
        )

    raw_namespace_files = source_observation.get("revision_namespace_files")
    if not isinstance(raw_namespace_files, list) or not raw_namespace_files:
        raise CurrentRestatedContractNotConnectedError(
            "snapshot receipt must pin a non-empty complete revision namespace inventory"
        )
    namespace_files: list[VerifiedRevisionNamespaceFileV1] = []
    seen_paths: set[str] = set()
    for index, item in enumerate(raw_namespace_files):
        if not isinstance(item, dict):
            raise CurrentRestatedContractNotConnectedError(
                f"revision namespace file {index} must be an object"
            )
        file_path = _source_context_regular_path(
            _source_context_receipt_path(
                item.get("path"), f"revision_namespace_files[{index}].path"
            ),
            f"revision namespace file {index}",
        )
        canonical_path = _source_context_path_key(file_path)
        if canonical_path in seen_paths:
            raise CurrentRestatedContractNotConnectedError(
                "snapshot receipt contains duplicate revision namespace paths"
            )
        seen_paths.add(canonical_path)
        file_sha256 = _source_context_check_file_pin(
            file_path,
            item,
            label=f"revision namespace file {index}",
        )
        namespace_files.append(
            VerifiedRevisionNamespaceFileV1(
                path=str(file_path),
                bytes=_source_context_nonnegative_int(
                    item.get("bytes"), f"revision_namespace_files[{index}].bytes"
                ),
                mtime_ns=_source_context_nonnegative_int(
                    item.get("mtime_ns"), f"revision_namespace_files[{index}].mtime_ns"
                ),
                sha256="sha256:" + file_sha256,
            )
        )

    expected_inventory = _source_context_scan_revision_namespace_inventory(
        source_path
    )
    receipt_inventory = {
        _source_context_path_key(Path(item.path)): item.sha256.removeprefix("sha256:")
        for item in namespace_files
    }
    expected_inventory_by_path = {
        _source_context_path_key(path): (namespace, digest)
        for path, namespace, digest in expected_inventory
    }
    if receipt_inventory != {
        path_key: digest for path_key, (_namespace, digest) in expected_inventory_by_path.items()
    }:
        raise CurrentRestatedContractNotConnectedError(
            "snapshot namespace pins do not match the complete required-root inventory"
        )

    cutoff_date = decision_utc.astimezone(
        ZoneInfo("Asia/Taipei")
    ).date()
    source_summary = check_daily_price_source_revision(
        database_path=source_path,
        decision_date=cutoff_date,
        allow_source_revision_research=True,
    )
    if (
        source_summary is None
        or source_summary.get("current_restated_research") is not True
        or source_summary.get("formal_historical_PIT") is not False
        or not _source_context_same_path(
            Path(str(source_summary.get("database_path", ""))), source_path
        )
        or source_summary.get("decision_date") != cutoff_date.isoformat()
    ):
        raise CurrentRestatedContractNotConnectedError(
            "original source database has no validated current-restated revision state"
        )
    evidence = source_summary.get("source_revision_evidence")
    if not isinstance(evidence, dict):
        raise CurrentRestatedContractNotConnectedError(
            "typed source revision evidence is missing"
        )
    namespaces = evidence.get("namespaces")
    if not isinstance(namespaces, list) or len(namespaces) != 4:
        raise CurrentRestatedContractNotConnectedError(
            "typed source revision evidence must contain all four namespaces"
        )
    expected_namespace_ids = {item.value for item in SourceEvidenceNamespaceV1}
    actual_namespace_ids: set[str] = set()
    gate_file_hashes: dict[str, set[str]] = {
        namespace.value: set() for namespace in SourceEvidenceNamespaceV1
    }
    gate_evidence_files: list[tuple[str, str, str]] = []
    gate_presence: dict[str, str] = {}
    gate_role_hashes: dict[str, dict[str, str]] = {
        namespace.value: {} for namespace in SourceEvidenceNamespaceV1
    }
    for namespace in namespaces:
        if not isinstance(namespace, dict):
            raise CurrentRestatedContractNotConnectedError(
                "typed source revision namespace is invalid"
            )
        namespace_id = namespace.get("namespace")
        if not isinstance(namespace_id, str) or namespace_id in actual_namespace_ids:
            raise CurrentRestatedContractNotConnectedError(
                "typed source revision namespace ids are invalid"
            )
        actual_namespace_ids.add(namespace_id)
        if namespace_id not in gate_file_hashes:
            raise CurrentRestatedContractNotConnectedError(
                "typed source revision namespace id is unsupported"
            )
        files = namespace.get("files")
        if not isinstance(files, list):
            raise CurrentRestatedContractNotConnectedError(
                "typed source revision namespace file list is invalid"
            )
        namespace_files_hashes: set[str] = set()
        namespace_role_ids: set[str] = set()
        for file_entry in files:
            if not isinstance(file_entry, dict):
                raise CurrentRestatedContractNotConnectedError(
                    "typed source revision file pin is invalid"
                )
            file_sha = _source_context_pin(
                file_entry.get("sha256"), "source_revision_evidence.sha256"
            )
            role_id = file_entry.get("role_id")
            if not isinstance(role_id, str) or not role_id.strip() or role_id in namespace_role_ids:
                raise CurrentRestatedContractNotConnectedError(
                    "typed source revision role ids are invalid or duplicated"
                )
            namespace_role_ids.add(role_id)
            namespace_files_hashes.add(file_sha)
            gate_role_hashes[namespace_id][role_id] = "sha256:" + file_sha
            gate_evidence_files.append(
                (namespace_id, role_id, "sha256:" + file_sha)
            )
        presence = namespace.get("presence")
        expected_presence = "present" if files else "empty"
        if presence != expected_presence:
            raise CurrentRestatedContractNotConnectedError(
                "typed source revision namespace presence does not match its file list"
            )
        gate_presence[namespace_id] = expected_presence
        gate_file_hashes[namespace_id] = namespace_files_hashes
    inventory_hashes_by_namespace: dict[str, set[str]] = {
        namespace.value: set() for namespace in SourceEvidenceNamespaceV1
    }
    for _path, namespace_id, digest in expected_inventory:
        inventory_hashes_by_namespace[namespace_id].add(digest)
    if (
        actual_namespace_ids != expected_namespace_ids
        or any(
            not gate_file_hashes[namespace_id].issubset(
                inventory_hashes_by_namespace[namespace_id]
            )
            for namespace_id in expected_namespace_ids
            if namespace_id
            != SourceEvidenceNamespaceV1.EXCLUDED_DAILY_PRICE_REVISION.value
        )
        or any(
            bool(gate_file_hashes[namespace_id])
            != (gate_presence[namespace_id] == "present")
            for namespace_id in expected_namespace_ids
        )
        or any(
            gate_presence[namespace_id] == "present"
            and not inventory_hashes_by_namespace[namespace_id]
            for namespace_id in expected_namespace_ids
        )
    ):
        raise CurrentRestatedContractNotConnectedError(
            "typed four-namespace evidence does not match its pinned namespace inventory"
        )
    raw_dependencies = source_summary.get("validated_revision_dependencies")
    if not isinstance(raw_dependencies, list):
        raise CurrentRestatedContractNotConnectedError(
            "validated physical revision dependency inventory is missing"
        )
    dependency_digest = _source_context_pin(
        source_summary.get("validated_revision_dependencies_sha256"),
        "validated_revision_dependencies_sha256",
    )
    if _source_context_canonical_sha256(raw_dependencies) != dependency_digest:
        raise CurrentRestatedContractNotConnectedError(
            "validated physical revision dependency digest is inconsistent"
        )
    source_data_root = source_path.parent.parent if source_path.parent.name.casefold() == "sqlite" else source_path.parent
    expected_inventory_by_path = {
        _source_context_path_key(path): (namespace_id, digest)
        for path, namespace_id, digest in expected_inventory
    }
    revision_dependencies: list[VerifiedRevisionDependencyV1] = []
    seen_dependency_roles: set[tuple[str, str]] = set()
    seen_dependency_paths: set[str] = set()
    captured_role_hashes: dict[str, str] = {}
    for index, item in enumerate(raw_dependencies):
        if not isinstance(item, dict):
            raise CurrentRestatedContractNotConnectedError(
                f"validated physical revision dependency {index} is invalid"
            )
        namespace_id = item.get("namespace")
        role_id = item.get("role_id")
        if (
            namespace_id
            != SourceEvidenceNamespaceV1.EXCLUDED_DAILY_PRICE_REVISION.value
            or not isinstance(role_id, str)
            or not role_id.strip()
            or (namespace_id, role_id) in seen_dependency_roles
        ):
            raise CurrentRestatedContractNotConnectedError(
                "validated physical revision dependency namespace/role is invalid"
            )
        seen_dependency_roles.add((namespace_id, role_id))
        dependency_path_value = _source_context_receipt_path(
            item.get("path"),
            f"validated_revision_dependencies[{index}].path",
        )
        dependency_path = _source_context_regular_path(
            dependency_path_value,
            f"validated physical revision dependency {role_id}",
        )
        try:
            dependency_path.relative_to(source_data_root.resolve(strict=True))
        except ValueError as exc:
            raise CurrentRestatedContractNotConnectedError(
                "validated physical revision dependency is outside the original data root"
            ) from exc
        dependency_path_key = _source_context_path_key(dependency_path)
        if dependency_path_key in seen_dependency_paths:
            raise CurrentRestatedContractNotConnectedError(
                "validated physical revision dependency path is duplicated"
            )
        seen_dependency_paths.add(dependency_path_key)
        dependency_sha256 = _source_context_pin(
            item.get("sha256"),
            f"validated_revision_dependencies[{index}].sha256",
        )
        dependency_bytes = _source_context_nonnegative_int(
            item.get("bytes"),
            f"validated_revision_dependencies[{index}].bytes",
        )
        dependency_mtime_ns = _source_context_nonnegative_int(
            item.get("mtime_ns"),
            f"validated_revision_dependencies[{index}].mtime_ns",
        )
        captured_at = _source_context_aware_utc(
            item.get("captured_at"),
            f"validated_revision_dependencies[{index}].captured_at",
        )
        current_sha256 = _source_context_check_file_pin(
            dependency_path,
            {
                "bytes": dependency_bytes,
                "mtime_ns": dependency_mtime_ns,
                "sha256": dependency_sha256,
            },
            label=f"validated physical revision dependency {role_id}",
        )
        inventory_pin = expected_inventory_by_path.get(dependency_path_key)
        if inventory_pin is not None and inventory_pin[1] != current_sha256:
            raise CurrentRestatedContractNotConnectedError(
                "excluded dependency physical bytes differ from the snapshot namespace pin"
            )
        captured_role_hashes[role_id] = "sha256:" + current_sha256
        revision_dependencies.append(
            VerifiedRevisionDependencyV1(
                namespace=namespace_id,
                role_id=role_id,
                path=str(dependency_path),
                bytes=dependency_bytes,
                mtime_ns=dependency_mtime_ns,
                sha256="sha256:" + current_sha256,
                captured_at=captured_at,
            )
        )
    excluded_namespace_id = (
        SourceEvidenceNamespaceV1.EXCLUDED_DAILY_PRICE_REVISION.value
    )
    if captured_role_hashes != gate_role_hashes[excluded_namespace_id]:
        raise CurrentRestatedContractNotConnectedError(
            "excluded typed roles do not exactly match same-capture physical dependencies"
        )
    evidence_sha256 = _source_context_pin(
        source_summary.get("source_revision_evidence_sha256"),
        "source_revision_evidence_sha256",
    )
    if evidence.get("digest_sha256") != evidence_sha256:
        raise CurrentRestatedContractNotConnectedError(
            "typed source revision evidence digest is inconsistent"
        )
    evidence_schema_version = evidence.get("schema_version")
    evidence_scope_id = evidence.get("scope_id")
    evidence_cutoff_date = evidence.get("cutoff_date")
    if (
        evidence_schema_version != SOURCE_REVISION_EVIDENCE_SCHEMA_V1
        or not isinstance(evidence_scope_id, str)
        or not evidence_scope_id
        or evidence_cutoff_date != cutoff_date.isoformat()
    ):
        raise CurrentRestatedContractNotConnectedError(
            "typed source revision evidence identity does not match its cutoff"
        )
    namespace_bundle_sha256 = _source_context_canonical_sha256(
        [
            {
                "path": item.path,
                "bytes": item.bytes,
                "mtime_ns": item.mtime_ns,
                "sha256": item.sha256,
            }
            for item in sorted(namespace_files, key=lambda row: row.path.casefold())
        ]
    )
    _source_context_check_file_pin(
        source_path, source_db, label="original source database recheck"
    )
    _source_context_check_file_pin(
        source_wal_path, source_wal, label="source WAL recheck"
    )
    _source_context_check_file_pin(
        snapshot_path, snapshot, label="snapshot database recheck"
    )
    for index, item in enumerate(namespace_files):
        _source_context_check_file_pin(
            Path(item.path),
            {
                "bytes": item.bytes,
                "mtime_ns": item.mtime_ns,
                "sha256": item.sha256,
            },
            label=f"revision namespace file {index} recheck",
        )
    inventory_after = _source_context_scan_revision_namespace_inventory(
        source_path
    )
    inventory_after_by_path = {
        _source_context_path_key(path): (namespace_id, digest)
        for path, namespace_id, digest in inventory_after
    }
    if inventory_after_by_path != expected_inventory_by_path:
        raise CurrentRestatedContractNotConnectedError(
            "original revision namespace inventory changed during context validation"
        )
    for dependency in revision_dependencies:
        _source_context_check_file_pin(
            Path(dependency.path),
            {
                "bytes": dependency.bytes,
                "mtime_ns": dependency.mtime_ns,
                "sha256": dependency.sha256,
            },
            label=f"revision dependency {dependency.role_id} recheck",
        )
    receipt_bytes_after = receipt_path.read_bytes()
    receipt_info_final = receipt_path.stat()
    if (
        hashlib.sha256(receipt_bytes_after).hexdigest() != receipt_sha256
        or len(receipt_bytes_after) != receipt_info_before.st_size
        or receipt_info_final.st_size != receipt_info_before.st_size
        or receipt_info_final.st_mtime_ns != receipt_info_before.st_mtime_ns
        or receipt_path.resolve(strict=True) != receipt_path
    ):
        raise CurrentRestatedContractNotConnectedError(
            "snapshot receipt changed during source-context validation"
        )
    revision_dependencies_verified_at = datetime.now(timezone.utc)
    dependency_payload = [
        {
            "namespace": item.namespace,
            "role_id": item.role_id,
            "path": item.path,
            "bytes": item.bytes,
            "mtime_ns": item.mtime_ns,
            "sha256": item.sha256,
            "captured_at": item.captured_at.isoformat(),
        }
        for item in sorted(
            revision_dependencies,
            key=lambda row: (row.namespace, row.role_id, row.path.casefold()),
        )
    ]
    revision_dependency_bundle_sha256 = _source_context_canonical_sha256(
        dependency_payload
    )
    return VerifiedCurrentRestatedSourceContext(
        source_database_path=str(source_path),
        source_database_sha256="sha256:" + source_db_sha256,
        source_wal_path=str(source_wal_path),
        source_wal_sha256="sha256:" + source_wal_sha256,
        snapshot_database_path=str(snapshot_path),
        snapshot_database_sha256="sha256:" + snapshot_sha256,
        snapshot_receipt_path=str(receipt_path),
        snapshot_receipt_sha256="sha256:" + receipt_sha256,
        decision_at=decision_utc,
        training_as_of=training_utc,
        source_observed_at=completed_at,
        source_generation=generation_after,
        revision_namespace_files=tuple(namespace_files),
        revision_namespace_bundle_sha256="sha256:" + namespace_bundle_sha256,
        source_revision_evidence_schema_version=str(evidence_schema_version),
        source_revision_evidence_scope_id=evidence_scope_id,
        source_revision_evidence_cutoff_date=str(evidence_cutoff_date),
        source_revision_evidence_sha256="sha256:" + evidence_sha256,
        source_revision_evidence_namespaces=tuple(sorted(actual_namespace_ids)),
        source_revision_evidence_files=tuple(
            sorted(gate_evidence_files, key=lambda item: (item[0], item[1]))
        ),
        revision_dependencies_verified_at=revision_dependencies_verified_at,
        revision_dependency_files=tuple(
            sorted(
                revision_dependencies,
                key=lambda row: (row.namespace, row.role_id, row.path.casefold()),
            )
        ),
        revision_dependency_bundle_sha256=(
            "sha256:" + revision_dependency_bundle_sha256
        ),
    )


def _collect_validated_source_revision_bundle(
    *,
    database_path: Path,
    cutoff: date,
    symbols: frozenset[str] | None,
    explicit_path: Path | None,
    allow_source_revision_research: bool,
) -> tuple[
    ValidatedSourceEvidenceV1,
    list[dict[str, str]],
    list[str],
    dict[str, Any] | None,
    tuple[VerifiedRevisionDependencyV1, ...],
]:
    """一次嚴格驗證四個 namespace，僅從已驗證 typed state 判斷修訂政策。"""
    from data_module import excluded_daily_price_revision
    from data_module import formal_market_revision
    from data_module import historical_session_revision

    states: list[dict[str, str]] = []
    blocked: list[str] = []

    market = formal_market_revision.inspect_market_revision_state(database_path)
    for run in market.runs:
        if run.state == "pending":
            raise DailyPriceSourceRevisionError(
                f"market revision run is pending: {run.run_id}"
            )
        if run.state == "applied" and cutoff >= date.fromisoformat(
            run.source_start_date
        ):
            blocked.append("market_revision")
        states.append(
            {
                "namespace": SourceEvidenceNamespaceV1.MARKET_REVISION.value,
                "run_id": run.run_id,
                "state": run.state,
                "source_start_date": run.source_start_date,
                "source_end_date": run.source_end_date,
            }
        )

    session_evidence, session_states = _inspect_session_revision_state(
        database_path
    )
    for state in session_states:
        if state["state"] == "pending":
            raise DailyPriceSourceRevisionError(
                f"historical session revision run is pending: {state['run_id']}"
            )
        if state["state"] == "applied" and cutoff >= date.fromisoformat(
            state["source_start_date"]
        ):
            blocked.append("historical_session_revision")
        states.append(
            {
                "namespace": SourceEvidenceNamespaceV1.HISTORICAL_SESSION_REVISION.value,
                **state,
            }
        )

    excluded_capture = excluded_daily_price_revision.collect_excluded_revision_capture(
        database_path
    )
    dependencies = tuple(
        VerifiedRevisionDependencyV1(
            namespace=item.namespace,
            role_id=item.role_id,
            path=item.path,
            bytes=item.bytes,
            mtime_ns=item.mtime_ns,
            sha256=item.sha256,
            captured_at=item.captured_at,
        )
        for item in excluded_capture.dependencies
    )
    for excluded_run in excluded_capture.runs:
        excluded_state = excluded_run.state
        source_start = excluded_run.source_start_date
        if excluded_state == "applied" and cutoff >= date.fromisoformat(source_start):
            blocked.append("excluded_daily_price_revision")
        states.append(
            {
                "namespace": SourceEvidenceNamespaceV1.EXCLUDED_DAILY_PRICE_REVISION.value,
                "run_id": excluded_run.run_id,
                "state": excluded_state,
                "source_start_date": source_start,
            }
        )
    excluded_evidence = excluded_capture.evidence

    daily_summary, daily_files = _inspect_daily_price_repair_receipts_once(
        database_path=database_path,
        decision=cutoff,
        symbols=symbols,
        explicit_path=explicit_path,
        strict_explicit_slots=False,
        allow_source_revision_research=allow_source_revision_research,
    )
    if daily_summary is not None:
        for receipt in daily_summary["checked_receipts"]:
            if int(receipt["relevant_row_count"]) > 0:
                blocked.append("daily_price_repair_receipt")
        for receipt in daily_summary["checked_receipts"]:
            states.append(
                {
                    "namespace": SourceEvidenceNamespaceV1.DAILY_PRICE_REPAIR_RECEIPT.value,
                    "run_id": str(receipt["receipt_hash"]),
                    "state": str(receipt["status"]),
                    "source_start_date": str(receipt["source_date"]),
                }
            )
    daily_evidence = ValidatedNamespaceEvidenceV1(
        namespace=SourceEvidenceNamespaceV1.DAILY_PRICE_REPAIR_RECEIPT,
        presence=(
            SourceEvidencePresenceV1.PRESENT
            if daily_files
            else SourceEvidencePresenceV1.EMPTY
        ),
        files=daily_files,
    )
    evidence_bundle = ValidatedSourceEvidenceV1(
        schema_version=SOURCE_REVISION_EVIDENCE_SCHEMA_V1,
        scope_id="ml_daily_price_revision_gate.v1",
        cutoff_date=cutoff,
        namespaces=(
            market.evidence,
            session_evidence,
            excluded_evidence,
            daily_evidence,
        ),
    )
    return evidence_bundle, states, sorted(set(blocked)), daily_summary, dependencies


def _inspect_session_revision_state(
    database_path: Path,
) -> tuple[ValidatedNamespaceEvidenceV1, list[dict[str, str]]]:
    """讀取 session revision 的既有嚴格 parser，另保留其已驗證狀態。"""
    from data_module import historical_session_revision

    receipt_root = historical_session_revision._session_receipt_root(database_path)
    if receipt_root is None:
        return (
            ValidatedNamespaceEvidenceV1(
                namespace=SourceEvidenceNamespaceV1.HISTORICAL_SESSION_REVISION,
                presence=SourceEvidencePresenceV1.EMPTY,
                files=(),
            ),
            [],
        )
    marker_paths = historical_session_revision._session_marker_paths(receipt_root)
    capture = historical_session_revision._SessionEvidenceCapture(receipt_root)
    files: list[ValidatedEvidenceFileV1] = []
    states: list[dict[str, str]] = []
    for marker_path, expected_run in marker_paths:
        run_role = historical_session_revision._session_run_role_id(
            marker_path, receipt_root
        )
        marker, plan = historical_session_revision._validated_plan(
            marker_path,
            database_path,
            capture=capture,
            run_role=run_role,
            expected_run=expected_run,
        )
        if marker_path.parent.resolve(strict=True) != expected_run:
            raise DailyPriceSourceRevisionError(
                f"historical session revision run changed while scanning: {marker_path}"
            )
        files.extend(capture.files)
        capture.files.clear()
        states.append(
            {
                "run_id": marker_path.parent.name,
                "state": str(marker["state"]),
                "source_start_date": date.fromisoformat(
                    str(plan["source_start_date"])
                ).isoformat(),
            }
        )
    return (
        ValidatedNamespaceEvidenceV1(
            namespace=SourceEvidenceNamespaceV1.HISTORICAL_SESSION_REVISION,
            presence=(
                SourceEvidencePresenceV1.PRESENT
                if files
                else SourceEvidencePresenceV1.EMPTY
            ),
            files=tuple(files),
        ),
        states,
    )


def _source_evidence_payload(
    evidence: ValidatedSourceEvidenceV1,
) -> dict[str, Any]:
    return {
        "schema_version": evidence.schema_version,
        "scope_id": evidence.scope_id,
        "cutoff_date": evidence.cutoff_date.isoformat(),
        "digest_sha256": evidence.digest_sha256,
        "namespaces": [
            {
                "namespace": namespace.namespace.value,
                "presence": namespace.presence.value,
                "digest_sha256": namespace.digest_sha256,
                "files": [
                    {"role_id": item.role_id, "sha256": item.sha256}
                    for item in namespace.files
                ],
            }
            for namespace in evidence.namespaces
        ],
    }


def collect_daily_price_repair_receipt_evidence(
    *,
    database_path: Path,
    decision_date: date | datetime | str,
    symbols: Iterable[str] | None = None,
    explicit_path: Path | None = None,
) -> ValidatedNamespaceEvidenceV1:
    """收集 direct daily-price receipt namespace 的同次 bytes 證據。

    此入口只負責 direct receipt namespace；同層的 market、session、excluded
    namespace 仍由其各自 collector 檢查。既有 public guard 仍保留那些 guard
    的呼叫順序與 ``dict | None`` 回傳 ABI。
    """

    cutoff = _as_date(decision_date)
    normalized_symbols = _normalized_receipt_symbols(symbols)
    _, evidence_files = _inspect_daily_price_repair_receipts_once(
        database_path=database_path,
        decision=cutoff,
        symbols=normalized_symbols,
        explicit_path=explicit_path,
        strict_explicit_slots=True,
    )
    presence = (
        SourceEvidencePresenceV1.PRESENT
        if evidence_files
        else SourceEvidencePresenceV1.EMPTY
    )
    return ValidatedNamespaceEvidenceV1(
        namespace=SourceEvidenceNamespaceV1.DAILY_PRICE_REPAIR_RECEIPT,
        presence=presence,
        files=evidence_files,
    )


def _normalized_receipt_symbols(
    symbols: Iterable[str] | None,
) -> frozenset[str] | None:
    normalized = (
        None
        if symbols is None
        else frozenset(str(symbol).strip() for symbol in symbols if str(symbol).strip())
    )
    if normalized is not None and not normalized:
        raise ValueError("symbols must not be empty when supplied")
    return normalized


def _inspect_daily_price_repair_receipts_once(
    *,
    database_path: Path,
    decision: date,
    symbols: frozenset[str] | None,
    explicit_path: Path | None,
    strict_explicit_slots: bool,
    allow_source_revision_research: bool = False,
) -> tuple[dict[str, Any] | None, tuple[ValidatedEvidenceFileV1, ...]]:
    """掃描候選一次，並以每份 receipt 的同次 bytes 同時產生摘要與證據。"""

    (
        receipts,
        automatic_receipts,
        database_root,
        automatic_sources,
    ) = _receipt_candidates_with_policy(
        database_path=database_path,
        explicit_path=explicit_path,
        strict_explicit_slots=strict_explicit_slots,
    )
    if not receipts:
        return None, ()

    summaries: list[dict[str, Any]] = []
    evidence_files: list[ValidatedEvidenceFileV1] = []
    handled_paths: set[Path] = set()
    for path in receipts:
        if path in handled_paths:
            continue
        automatic = path in automatic_receipts
        containment_root = database_root if automatic else None
        automatic_source_path = automatic_sources.get(path)
        pair_paths: tuple[Path, Path] | None = None
        if allow_source_revision_research:
            if path.name == "pending.json":
                pair_paths = (path, path.with_name("receipt.json"))
            elif path.name == "receipt.json":
                pending_path = path.with_name("pending.json")
                if pending_path.exists():
                    pair_paths = (pending_path, path)

        if pair_paths is not None:
            pending_path, final_path = pair_paths
            pending_source = (
                automatic_sources.get(pending_path)
                if pending_path in automatic_receipts
                else pending_path
            )
            final_source = (
                automatic_sources.get(final_path)
                if final_path in automatic_receipts
                else final_path
            )
            pair_root = database_root if (
                pending_path in automatic_receipts or final_path in automatic_receipts
            ) else None
            if pair_root is not None:
                if pending_source is None or final_source is None:
                    raise DailyPriceSourceRevisionError(
                        "completed daily-price repair pair has an invalid automatic path"
                    )
            pending_capture = _capture_daily_repair_receipt(
                pending_path,
                containment_root=pair_root,
                automatic_source_path=pending_source,
                label="pending marker",
            )
            if (
                pending_capture.payload.get("receipt_kind")
                == "historical_price_spike_repair_pending"
                and pending_capture.payload.get("status")
                != "applied_receipt_written"
            ):
                raise DailyPriceSourceRevisionError(
                    "daily-price repair pending marker is unresolved and blocks all symbols: "
                    f"{pending_path}"
                )
            final_capture = _capture_daily_repair_receipt(
                final_path,
                containment_root=pair_root,
                automatic_source_path=final_source,
                label="final receipt",
            )
            _validate_completed_daily_repair_pair(
                pending_capture,
                final_capture,
                database_path=database_path,
            )
            summary, _receipt_sha256 = _check_receipt_with_evidence(
                path=final_path,
                decision=decision,
                symbols=symbols,
                containment_root=pair_root,
                automatic_source_path=final_source,
                allow_source_revision_research=True,
                captured_receipt=final_capture,
            )
            summary["completed_pending_pair"] = {
                "pending_receipt_hash": "sha256:" + pending_capture.sha256,
                "final_receipt_hash": "sha256:" + final_capture.sha256,
                "source_date": summary["source_date"],
                "affected_row_count": summary["affected_row_count"],
            }
            summaries.append(summary)
            for captured in (pending_capture, final_capture):
                role_path = captured.path
                evidence_files.append(
                    ValidatedEvidenceFileV1(
                        role_id=_receipt_role_id(
                            role_path,
                            database_root=database_root,
                            is_automatic=(
                                (pending_path if captured is pending_capture else final_path)
                                in automatic_receipts
                            ),
                        ),
                        sha256=captured.sha256,
                    )
                )
            handled_paths.update({pending_path, final_path})
            continue

        summary, receipt_sha256 = _check_receipt_with_evidence(
            path=path,
            decision=decision,
            symbols=symbols,
            containment_root=containment_root,
            automatic_source_path=automatic_source_path,
            allow_source_revision_research=allow_source_revision_research,
        )
        summaries.append(summary)
        resolved_path = Path(str(summary["receipt_path"]))
        evidence_files.append(
            ValidatedEvidenceFileV1(
                role_id=_receipt_role_id(
                    resolved_path,
                    database_root=database_root,
                    is_automatic=(path in automatic_receipts),
                ),
                sha256=receipt_sha256,
            )
        )

    summary_result = {
        "schema_version": REPAIR_SCHEMA,
        "checked_receipt_count": len(evidence_files),
        "checked_receipts": summaries,
        "relevant_row_count": sum(
            int(summary["relevant_row_count"]) for summary in summaries
        ),
        "policy": "fail_closed_until_repaired_source_rebuild",
    }
    return summary_result, tuple(evidence_files)


def _receipt_role_id(
    path: Path,
    *,
    database_root: Path,
    is_automatic: bool,
) -> str:
    resolved_path = path.resolve(strict=True)
    if is_automatic:
        try:
            relative_path = resolved_path.relative_to(database_root).as_posix()
        except ValueError as exc:
            raise DailyPriceSourceRevisionError(
                f"automatic source revision receipt is outside data root: {resolved_path}"
            ) from exc
        role_token = base64.urlsafe_b64encode(
            relative_path.encode("utf-8")
        ).decode("ascii").rstrip("=")
        return f"automatic/{role_token}"
    path_identity = resolved_path.as_posix().encode("utf-8")
    return "explicit/" + hashlib.sha256(path_identity).hexdigest()


def _capture_daily_repair_receipt(
    path: Path,
    *,
    containment_root: Path | None,
    automatic_source_path: Path | None,
    label: str,
) -> _CapturedDailyRepairReceipt:
    if containment_root is not None:
        source_path = automatic_source_path or path
        try:
            resolved = _resolve_automatic_receipt_path(
                source_path,
                database_root=containment_root,
                require_file=True,
            )
        except DailyPriceSourceRevisionError as exc:
            raise DailyPriceSourceRevisionError(
                f"automatic source revision {label} is missing or unresolved: {source_path}"
            ) from exc
        if resolved != path:
            raise DailyPriceSourceRevisionError(
                f"automatic {label} path differs from its fixed receipt slot: {path}"
            )
        lexical_path = source_path
    else:
        lexical_path = path
        if lexical_path.is_symlink():
            raise DailyPriceSourceRevisionError(
                f"source revision {label} must not be linked: {lexical_path}"
            )
        try:
            resolved = lexical_path.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise DailyPriceSourceRevisionError(
                f"source revision {label} is missing or unresolved: {lexical_path}"
            ) from exc
    _source_context_reject_reparse(lexical_path, f"source revision {label}")
    try:
        info_before = resolved.stat()
        if not stat.S_ISREG(info_before.st_mode):
            raise DailyPriceSourceRevisionError(
                f"source revision {label} is not a regular file: {resolved}"
            )
        receipt_bytes = resolved.read_bytes()
        info_after = resolved.stat()
        resolved_after = lexical_path.resolve(strict=True)
    except DailyPriceSourceRevisionError:
        raise
    except (OSError, RuntimeError) as exc:
        raise DailyPriceSourceRevisionError(
            f"source revision {label} is unreadable: {resolved}"
        ) from exc
    _source_context_reject_reparse(lexical_path, f"source revision {label}")
    if (
        resolved_after != resolved
        or len(receipt_bytes) != info_before.st_size
        or len(receipt_bytes) != info_after.st_size
        or info_before.st_size != info_after.st_size
        or info_before.st_mtime_ns != info_after.st_mtime_ns
    ):
        raise DailyPriceSourceRevisionError(
            f"source revision {label} changed while being captured: {resolved}"
        )
    try:
        payload = json.loads(receipt_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DailyPriceSourceRevisionError(
            f"source revision {label} is unreadable: {resolved}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise DailyPriceSourceRevisionError(
            f"source revision {label} must be a JSON object: {resolved}"
        )
    return _CapturedDailyRepairReceipt(
        path=resolved,
        payload=payload,
        sha256=hashlib.sha256(receipt_bytes).hexdigest(),
        bytes=len(receipt_bytes),
        mtime_ns=info_after.st_mtime_ns,
    )


def _validate_completed_daily_repair_pair(
    pending_capture: _CapturedDailyRepairReceipt,
    final_capture: _CapturedDailyRepairReceipt,
    *,
    database_path: Path,
) -> None:
    pending_path = pending_capture.path
    final_path = final_capture.path
    if (
        pending_path.name != "pending.json"
        or final_path.name != "receipt.json"
        or pending_path.parent != final_path.parent
    ):
        raise DailyPriceSourceRevisionError(
            "completed daily-price repair pair must use fixed pending.json and sibling receipt.json"
        )
    if pending_capture.payload.get("allowlist_count") is not None and type(
        pending_capture.payload.get("allowlist_count")
    ) is not int:
        raise DailyPriceSourceRevisionError(
            f"daily-price pending allowlist_count must be an integer: {pending_path}"
        )
    if type(final_capture.payload.get("allowlist_count")) is not int:
        raise DailyPriceSourceRevisionError(
            f"daily-price final allowlist_count must be an integer: {final_path}"
        )
    try:
        from data_module import daily_price_revision_write_guard

        daily_price_revision_write_guard._verify_payload_hash(
            final_capture.payload, final_path
        )
        daily_price_revision_write_guard._scope_from_receipt(
            final_capture.payload, database_path.resolve(), final_path
        )
        daily_price_revision_write_guard._validate_completed_pending(
            pending_capture.payload,
            final_capture.payload,
            database_path.resolve(),
            pending_path,
        )
    except daily_price_revision_write_guard.DailyPriceRevisionWriteError as exc:
        raise DailyPriceSourceRevisionError(
            f"completed daily-price repair pair is invalid: {exc}"
        ) from exc


def _check_receipt(
    *,
    path: Path,
    decision: date,
    symbols: frozenset[str] | None,
    containment_root: Path | None = None,
    automatic_source_path: Path | None = None,
) -> dict[str, Any]:
    summary, _receipt_sha256 = _check_receipt_with_evidence(
        path=path,
        decision=decision,
        symbols=symbols,
        containment_root=containment_root,
        automatic_source_path=automatic_source_path,
    )
    return summary


def _check_receipt_with_evidence(
    *,
    path: Path,
    decision: date,
    symbols: frozenset[str] | None,
    containment_root: Path | None = None,
    automatic_source_path: Path | None = None,
    allow_source_revision_research: bool = False,
    captured_receipt: _CapturedDailyRepairReceipt | None = None,
) -> tuple[dict[str, Any], str]:
    if containment_root is None:
        path = path.resolve()
    else:
        source_path = automatic_source_path or path
        expected_path = path
        path = _resolve_automatic_receipt_path(
            source_path,
            database_root=containment_root,
            require_file=True,
        )
        if path != expected_path:
            raise DailyPriceSourceRevisionError(
                f"automatic source revision receipt changed before read: {expected_path}"
            )
    if not path.is_file() or (containment_root is None and path.is_symlink()):
        raise DailyPriceSourceRevisionError(
            f"source revision receipt is missing: {path}"
        )
    if captured_receipt is None:
        captured_receipt = _capture_daily_repair_receipt(
            path,
            containment_root=containment_root,
            automatic_source_path=automatic_source_path,
            label="receipt",
        )
    elif captured_receipt.path != path:
        raise DailyPriceSourceRevisionError(
            f"captured source revision receipt path mismatch: {path}"
        )
    payload = captured_receipt.payload
    if containment_root is not None:
        current_path = _resolve_automatic_receipt_path(
            automatic_source_path or path,
            database_root=containment_root,
            require_file=True,
        )
        if current_path != path:
            raise DailyPriceSourceRevisionError(
                f"automatic source revision receipt changed during read: {path}"
            )
    receipt_sha256 = captured_receipt.sha256
    receipt_hash = f"sha256:{receipt_sha256}"
    if not isinstance(payload, Mapping):
        raise DailyPriceSourceRevisionError(
            f"source revision receipt must be a JSON object: {path}"
        )
    if payload.get("schema_version") != REPAIR_SCHEMA:
        raise DailyPriceSourceRevisionError(
            "source revision receipt schema is unsupported; expected "
            f"{REPAIR_SCHEMA}: {path}"
        )
    receipt_kind = payload.get("receipt_kind")
    if type(receipt_kind) is not str or receipt_kind not in {
        "historical_price_spike_repair_pending",
        "historical_price_spike_repair",
    }:
        raise DailyPriceSourceRevisionError(
            "historical price repair receipt kind is unsupported: "
            f"{path}"
        )
    status = payload.get("status")
    if receipt_kind == "historical_price_spike_repair" and (
        type(status) is not str or status != "applied"
    ):
        raise DailyPriceSourceRevisionError(
            f"historical price repair receipt status is invalid: {path}"
        )

    source_date = _required_date(payload.get("source_date"), "source_date", path)
    raw_rows = payload.get("rows")
    if raw_rows is not None and not isinstance(raw_rows, list):
        raise DailyPriceSourceRevisionError(
            f"historical price repair receipt rows must be a list: {path}"
        )

    rows: list[tuple[date, str]] = []
    if isinstance(raw_rows, list):
        for index, raw_row in enumerate(raw_rows):
            if not isinstance(raw_row, Mapping):
                raise DailyPriceSourceRevisionError(
                    f"historical price repair receipt row {index} is invalid: {path}"
                )
            symbol = _row_symbol(raw_row)
            if not symbol:
                raise DailyPriceSourceRevisionError(
                    f"historical price repair receipt row {index} requires symbol: {path}"
                )
            row_date = _required_date(
                raw_row.get("date", raw_row.get("source_date", source_date.isoformat())),
                f"row {index} date",
                path,
            )
            if row_date != source_date:
                raise DailyPriceSourceRevisionError(
                    f"historical price repair receipt row {index} is outside source_date: {path}"
                )
            rows.append((row_date, symbol))

    try:
        allowlist_count = int(payload.get("allowlist_count", len(rows)))
    except (TypeError, ValueError) as exc:
        raise DailyPriceSourceRevisionError(
            f"historical price repair receipt allowlist_count is invalid: {path}"
        ) from exc
    if allowlist_count <= 0:
        raise DailyPriceSourceRevisionError(
            f"historical price repair receipt allowlist_count must be positive: {path}"
        )
    if rows and allowlist_count != len(rows):
        raise DailyPriceSourceRevisionError(
            "historical price repair receipt allowlist_count does not match rows: "
            f"{path}"
        )

    # Pending sidecar 刻意省略完整 rows；空的 final affected list 也保守處理，
    # 避免空 ``affected_rows`` 靜默繞過修訂 hold。
    all_symbols = not rows
    affected_rows = rows or [(source_date, "<all-symbols>")]
    relevant_rows = [
        (row_date, symbol)
        for row_date, symbol in affected_rows
        if row_date <= decision
        and (symbols is None or all_symbols or symbol in symbols)
    ]
    known_at = next(
        (
            str(payload[key])
            for key in ("corrected_at", "created_at", "official_capture_at")
            if isinstance(payload.get(key), str) and payload.get(key)
        ),
        None,
    )
    summary: dict[str, Any] = {
        "schema_version": REPAIR_SCHEMA,
        "receipt_path": str(path),
        "receipt_hash": receipt_hash,
        "receipt_kind": str(payload.get("receipt_kind", "")),
        "status": str(payload.get("status", "")),
        "source_date": source_date.isoformat(),
        "known_at": known_at,
        "known_after_decision": None,
        "affected_row_count": allowlist_count,
        "scope_mode": "all_symbols_conservative" if all_symbols else "row_exact",
        "relevant_row_count": len(relevant_rows),
        "relevant_dates": sorted({row_date.isoformat() for row_date, _ in relevant_rows}),
        "relevant_symbols": (
            ["<all-requested-symbols>"]
            if all_symbols and relevant_rows
            else sorted({symbol for _, symbol in relevant_rows})
        ),
        "policy": "fail_closed_until_repaired_source_rebuild",
    }
    if relevant_rows:
        if not allow_source_revision_research:
            raise DailyPriceSourceRevisionError(
                "historical price repair receipt blocks this PIT prefix; "
                f"source_date={source_date.isoformat()} decision={decision.isoformat()} "
                f"status={payload.get('status', '')!s} path={path}; "
                "rebuild features/labels with a revision-aware research or formal process"
            )
        summary["policy"] = "revision_aware_research"
        summary["market_revision_blocks_historical_pit"] = True
        summary["research_only"] = True
    return summary, receipt_sha256


def _as_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if len(text) >= 8 and text[:8].isdigit():
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    return date.fromisoformat(text[:10])


def _source_context_aware_utc(
    value: object,
    field_name: str,
) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip())
        except ValueError as exc:
            raise CurrentRestatedContractNotConnectedError(
                f"{field_name} must be an aware ISO timestamp"
            ) from exc
    else:
        raise CurrentRestatedContractNotConnectedError(
            f"{field_name} must be an aware ISO timestamp"
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CurrentRestatedContractNotConnectedError(
            f"{field_name} must include an explicit timezone"
        )
    return parsed.astimezone(timezone.utc)


def _source_context_pin(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise CurrentRestatedContractNotConnectedError(
            f"{field_name} must be a SHA-256 string"
        )
    cleaned = value.strip().lower()
    if cleaned.startswith("sha256:"):
        cleaned = cleaned[7:]
    if len(cleaned) != 64 or any(
        character not in "0123456789abcdef" for character in cleaned
    ):
        raise CurrentRestatedContractNotConnectedError(
            f"{field_name} must contain exactly 64 hexadecimal characters"
        )
    return cleaned


def _source_context_nonnegative_int(value: object, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise CurrentRestatedContractNotConnectedError(
            f"{field_name} must be a non-negative integer"
        )
    return value


def _source_context_receipt_path(value: object, field_name: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise CurrentRestatedContractNotConnectedError(
            f"{field_name} must be an absolute path"
        )
    path = Path(value.strip())
    if not path.is_absolute():
        raise CurrentRestatedContractNotConnectedError(
            f"{field_name} must be an absolute path"
        )
    return path


def _source_context_regular_path(path: Path, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise CurrentRestatedContractNotConnectedError(
            f"{label} path cannot be resolved: {path}"
        ) from exc
    _source_context_reject_reparse(path, label)
    try:
        info = resolved.lstat()
    except OSError as exc:
        raise CurrentRestatedContractNotConnectedError(
            f"{label} cannot be inspected: {resolved}"
        ) from exc
    if not stat.S_ISREG(info.st_mode):
        raise CurrentRestatedContractNotConnectedError(
            f"{label} is not a regular file: {resolved}"
        )
    return resolved


def _source_context_reject_reparse(path: Path, label: str) -> None:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.parts[0])
    for part in absolute.parts[1:]:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            raise CurrentRestatedContractNotConnectedError(
                f"{label} path component is missing: {current}"
            )
        except OSError as exc:
            raise CurrentRestatedContractNotConnectedError(
                f"{label} path component cannot be inspected: {current}"
            ) from exc
        attributes = getattr(info, "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        is_junction = getattr(current, "is_junction", None)
        if (
            stat.S_ISLNK(info.st_mode)
            or bool(attributes & reparse_flag)
            or (callable(is_junction) and is_junction())
        ):
            raise CurrentRestatedContractNotConnectedError(
                f"{label} path cannot traverse a symlink or junction: {current}"
            )


def _source_context_same_path(left: Path, right: Path) -> bool:
    return _source_context_path_key(left) == _source_context_path_key(right)


def _source_context_path_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve(strict=True))).casefold()


def _source_context_check_file_pin(
    path: Path,
    payload: Mapping[str, Any],
    *,
    label: str,
) -> str:
    expected_bytes = _source_context_nonnegative_int(
        payload.get("bytes"), f"{label}.bytes"
    )
    expected_mtime_ns = _source_context_nonnegative_int(
        payload.get("mtime_ns"), f"{label}.mtime_ns"
    )
    expected_sha256 = _source_context_pin(
        payload.get("sha256"), f"{label}.sha256"
    )
    try:
        resolved_before = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise CurrentRestatedContractNotConnectedError(
            f"{label} path changed before hashing"
        ) from exc
    _source_context_reject_reparse(path, label)
    info = resolved_before.stat()
    if info.st_size != expected_bytes:
        raise CurrentRestatedContractNotConnectedError(
            f"{label} byte length differs from its receipt pin"
        )
    if getattr(info, "st_mtime_ns", int(info.st_mtime * 1_000_000_000)) != expected_mtime_ns:
        raise CurrentRestatedContractNotConnectedError(
            f"{label} modification timestamp differs from its receipt pin"
        )
    digest = hashlib.sha256()
    try:
        with resolved_before.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise CurrentRestatedContractNotConnectedError(
            f"{label} bytes cannot be read"
        ) from exc
    actual_sha256 = digest.hexdigest()
    try:
        resolved_after = path.resolve(strict=True)
        after_info = resolved_after.stat()
    except (OSError, RuntimeError) as exc:
        raise CurrentRestatedContractNotConnectedError(
            f"{label} path changed after hashing"
        ) from exc
    _source_context_reject_reparse(path, label)
    if (
        resolved_after != resolved_before
        or info.st_size != after_info.st_size
        or getattr(info, "st_mtime_ns", int(info.st_mtime * 1_000_000_000))
        != getattr(after_info, "st_mtime_ns", int(after_info.st_mtime * 1_000_000_000))
    ):
        raise CurrentRestatedContractNotConnectedError(
            f"{label} changed while hashing"
        )
    if actual_sha256 != expected_sha256:
        raise CurrentRestatedContractNotConnectedError(
            f"{label} actual-bytes SHA-256 differs from its receipt pin"
        )
    return actual_sha256


def _source_context_scan_revision_namespace_inventory(
    database_path: Path,
) -> tuple[tuple[Path, str, str], ...]:
    """掃描四個固定來源 namespace root 的完整一般檔案清冊。"""

    from data_module import excluded_daily_price_revision
    from data_module import formal_market_revision
    from data_module import historical_session_revision

    data_root = database_path.resolve(strict=True).parent
    if data_root.name.casefold() == "sqlite":
        data_root = data_root.parent
    namespace_roots = (
        (
            SourceEvidenceNamespaceV1.DAILY_PRICE_REPAIR_RECEIPT.value,
            data_root / REPAIR_RECEIPT_RELATIVE_DIR,
        ),
        (
            SourceEvidenceNamespaceV1.MARKET_REVISION.value,
            data_root / formal_market_revision.RECEIPT_DIR,
        ),
        (
            SourceEvidenceNamespaceV1.HISTORICAL_SESSION_REVISION.value,
            data_root / historical_session_revision.RECEIPT_DIR,
        ),
        (
            SourceEvidenceNamespaceV1.EXCLUDED_DAILY_PRICE_REVISION.value,
            data_root / excluded_daily_price_revision.RECEIPT_DIR,
        ),
    )
    inventory: list[tuple[Path, str, str]] = []
    seen_paths: set[str] = set()
    for namespace_id, lexical_root in namespace_roots:
        root = _source_context_optional_directory(lexical_root, namespace_id)
        if root is None:
            continue
        stack = [root]
        while stack:
            directory = stack.pop()
            before_names = _source_context_directory_names(directory, namespace_id)
            children: list[Path] = []
            for name in before_names:
                candidate = directory / name
                _source_context_reject_reparse(candidate, namespace_id)
                try:
                    resolved = candidate.resolve(strict=True)
                    info = candidate.lstat()
                except (OSError, RuntimeError) as exc:
                    raise CurrentRestatedContractNotConnectedError(
                        f"{namespace_id} inventory entry cannot be resolved"
                    ) from exc
                try:
                    resolved.relative_to(root)
                except ValueError as exc:
                    raise CurrentRestatedContractNotConnectedError(
                        f"{namespace_id} inventory entry escapes its fixed root"
                    ) from exc
                mode = info.st_mode
                if stat.S_ISDIR(mode):
                    children.append(resolved)
                    continue
                if not stat.S_ISREG(mode):
                    raise CurrentRestatedContractNotConnectedError(
                        f"{namespace_id} inventory contains a non-regular entry"
                    )
                path_key = _source_context_path_key(resolved)
                if path_key in seen_paths:
                    raise CurrentRestatedContractNotConnectedError(
                        "revision namespace roots contain duplicate path aliases"
                    )
                seen_paths.add(path_key)
                digest = hashlib.sha256()
                try:
                    with resolved.open("rb") as stream:
                        while chunk := stream.read(1024 * 1024):
                            digest.update(chunk)
                    after_info = resolved.stat()
                except OSError as exc:
                    raise CurrentRestatedContractNotConnectedError(
                        f"{namespace_id} inventory file cannot be read"
                    ) from exc
                if (
                    info.st_size != after_info.st_size
                    or getattr(info, "st_mtime_ns", int(info.st_mtime * 1_000_000_000))
                    != getattr(
                        after_info,
                        "st_mtime_ns",
                        int(after_info.st_mtime * 1_000_000_000),
                    )
                ):
                    raise CurrentRestatedContractNotConnectedError(
                        f"{namespace_id} inventory file changed while being read"
                    )
                inventory.append((resolved, namespace_id, digest.hexdigest()))
            if _source_context_directory_names(directory, namespace_id) != before_names:
                raise CurrentRestatedContractNotConnectedError(
                    f"{namespace_id} inventory directory changed while being scanned"
                )
            stack.extend(reversed(children))
    return tuple(sorted(inventory, key=lambda item: _source_context_path_key(item[0])))


def _source_context_optional_directory(path: Path, label: str) -> Path | None:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.parts[0])
    for part in absolute.parts[1:]:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise CurrentRestatedContractNotConnectedError(
                f"{label} namespace root cannot be inspected"
            ) from exc
        attributes = getattr(info, "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        is_junction = getattr(current, "is_junction", None)
        if (
            stat.S_ISLNK(info.st_mode)
            or bool(attributes & reparse_flag)
            or (callable(is_junction) and is_junction())
        ):
            raise CurrentRestatedContractNotConnectedError(
                f"{label} namespace root cannot traverse a symlink or junction"
            )
        if current != absolute and not stat.S_ISDIR(info.st_mode):
            raise CurrentRestatedContractNotConnectedError(
                f"{label} namespace root ancestor is not a directory"
            )
    try:
        resolved = absolute.resolve(strict=True)
        info = resolved.lstat()
    except (OSError, RuntimeError) as exc:
        raise CurrentRestatedContractNotConnectedError(
            f"{label} namespace root cannot be resolved"
        ) from exc
    if not stat.S_ISDIR(info.st_mode):
        raise CurrentRestatedContractNotConnectedError(
            f"{label} namespace root is not a directory"
        )
    return resolved


def _source_context_directory_names(path: Path, label: str) -> tuple[str, ...]:
    try:
        with os.scandir(path) as entries:
            return tuple(sorted(entry.name for entry in entries))
    except OSError as exc:
        raise CurrentRestatedContractNotConnectedError(
            f"{label} namespace directory cannot be completely enumerated"
        ) from exc


def _source_context_canonical_sha256(payload: object) -> str:
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CurrentRestatedContractNotConnectedError(
            "source namespace bundle is not canonical JSON"
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def _required_date(value: object, label: str, path: Path) -> date:
    if value is None or not str(value).strip() or str(value).strip().casefold() == "none":
        raise DailyPriceSourceRevisionError(
            f"historical price repair receipt requires {label}: {path}"
        )
    try:
        return _as_date(str(value))
    except (TypeError, ValueError) as exc:
        raise DailyPriceSourceRevisionError(
            f"historical price repair receipt {label} is invalid: {path}"
        ) from exc


def _row_symbol(row: Mapping[str, Any]) -> str:
    value = row.get("symbol") or row.get("stock_code") or row.get("證券代號")
    symbol = "" if value is None else str(value).strip()
    if symbol.endswith(".0") and symbol[:-2].isdigit():
        symbol = symbol[:-2]
    return symbol.zfill(4) if symbol.isdigit() else symbol
