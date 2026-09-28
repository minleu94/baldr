"""個人推薦校準候選的唯讀、具預算清冊。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sqlite3
import tempfile
from typing import Any, Callable, Mapping

from app_module.recommendation.personal_use_policy import (
    PersonalCalibrationCandidateV1,
    RecommendationPersonalUsePolicyV2,
    load_personal_use_policy_snapshot,
)
from app_module.recommendation_learning_paths import (
    resolve_recommendation_learning_paths,
)


PERSONAL_CANDIDATE_INVENTORY_SCHEMA_V1 = "personal-calibration-candidate-inventory.v1"
MAX_RUN_ROOTS = 200
MAX_CANDIDATES = 500
MAX_DIRECTORY_ENTRIES = 10_000
MAX_CANDIDATE_JSON_BYTES = 1024 * 1024
MAX_MANIFEST_JSON_BYTES = 256 * 1024
MAX_LINEAGE_JSON_BYTES = 4 * 1024 * 1024
MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
MAX_SOURCE_PROOF_MANIFESTS = 2
MAX_SOURCE_PROOF_DECISION_DATES = 64
MAX_SOURCE_PROOF_SYMBOLS = 32
MAX_SOURCE_PROOF_SAMPLES = 2048
MAX_SOURCE_PROOF_HISTORY_DAYS = 730
MAX_SOURCE_PROOF_CONTRACT_ROWS = 250_000
MAX_SOURCE_PROOF_DATABASE_BYTES = 8 * 1024 * 1024 * 1024
MAX_REPLAY_MANIFEST_JSON_BYTES = 16 * 1024 * 1024
_TRUSTED_SOURCE_IDS = {
    "technical": "twse.mi_index.daily_price+tpex.daily_close_quotes",
    "corporate_actions": "official_market_event_publication",
}
_HASH_CHUNK_BYTES = 1024 * 1024
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_DATASET_ID_RE = re.compile(r"^recommendation-dataset-[0-9a-f]{16}$")


class PersonalCandidateInventoryError(ValueError):
    """清冊根目錄或候選輸入不符合唯讀邊界。"""


class PersonalCandidateInventoryCancelled(PersonalCandidateInventoryError):
    """呼叫端取消清冊或選中候選的完整檢查。"""


@dataclass(frozen=True)
class PersonalCandidateInventoryProgressV1:
    stage: str
    completed: int
    total: int | None
    current_path: str | None = None


@dataclass
class _DirectoryEntryBudget:
    limit: int = MAX_DIRECTORY_ENTRIES
    observed: int = 0
    exhausted: bool = False

    def consume(self) -> bool:
        if self.observed >= self.limit:
            self.exhausted = True
            return False
        self.observed += 1
        return True


@dataclass(frozen=True)
class PersonalCandidateInventoryEntryV1:
    candidate_id: str | None
    candidate_root: str
    status: str
    reason_code: str
    display_label: str
    candidate_frozen_at: str | None
    training_as_of: str | None
    training_semantics: str | None
    decision_time_eligible: bool | None
    dataset_id: str | None
    training_row_count: int | None
    calibration_sample_count: int | None
    calibration_gap_bp: int | None
    candidate_blockers: tuple[str, ...]
    next_step: str
    candidate: PersonalCalibrationCandidateV1 | None = None
    source_time_basis: str | None = None
    research_only: bool | None = None
    official_historical_pit_verified: bool | None = None


@dataclass(frozen=True)
class PersonalCandidateInventorySnapshotV1:
    learning_root: str
    status: str
    entries: tuple[PersonalCandidateInventoryEntryV1, ...]
    run_roots_scanned: int
    candidates_scanned: int
    truncated: bool
    warnings: tuple[str, ...]
    next_step: str


ProgressCallback = Callable[[PersonalCandidateInventoryProgressV1], None]
CancellationCheck = Callable[[], bool]


def list_personal_calibration_candidates(
    *,
    data_root: str | Path | None = None,
    explicit_output_root: str | Path | None = None,
    progress_callback: ProgressCallback | None = None,
    cancellation_requested: CancellationCheck | None = None,
) -> PersonalCandidateInventorySnapshotV1:
    """列舉固定深度內的候選摘要；不雜湊模型 artifact，也不產生可保存 pins。"""

    learning_root = _learning_root(data_root, explicit_output_root)
    runs_root = learning_root / "runs"
    try:
        runs_root.lstat()
    except FileNotFoundError:
        return PersonalCandidateInventorySnapshotV1(
            learning_root=str(learning_root),
            status="empty",
            entries=(),
            run_roots_scanned=0,
            candidates_scanned=0,
            truncated=False,
            warnings=(),
            next_step="完成一次具完整 lineage 的個人校準訓練後，再重新整理候選清冊。",
        )
    except OSError:
        return PersonalCandidateInventorySnapshotV1(
            learning_root=str(learning_root),
            status="incomplete",
            entries=(),
            run_roots_scanned=0,
            candidates_scanned=0,
            truncated=False,
            warnings=("runs_directory_unreadable",),
            next_step="無法讀取 learning root 的 runs 目錄；檢查本機路徑與讀取權限後重試。",
        )
    try:
        _ensure_directory_inside(runs_root, learning_root)
    except (OSError, PersonalCandidateInventoryError):
        return PersonalCandidateInventorySnapshotV1(
            learning_root=str(learning_root),
            status="incomplete",
            entries=(),
            run_roots_scanned=0,
            candidates_scanned=0,
            truncated=False,
            warnings=("runs_directory_unsafe_or_unreadable",),
            next_step="runs 目錄無法安全讀取；檢查 learning root 權限與目錄完整性。",
        )

    warnings: list[str] = []
    budget = _DirectoryEntryBudget(limit=MAX_DIRECTORY_ENTRIES)
    run_roots, run_truncated, discovery_warnings = _discover_run_candidate_roots(
        runs_root,
        budget=budget,
        progress_callback=progress_callback,
        cancellation_requested=cancellation_requested,
    )
    warnings.extend(discovery_warnings)

    entries: list[PersonalCandidateInventoryEntryV1] = []
    candidates_scanned = 0
    truncated = run_truncated
    for run_index, (run_root, candidates_dir) in enumerate(run_roots, start=1):
        _check_cancelled(cancellation_requested)
        _emit_progress(
            progress_callback,
            stage="list_run_root",
            completed=run_index,
            total=len(run_roots),
            path=run_root,
        )
        candidate_dirs, candidate_limit_reached = _bounded_child_directories(
            candidates_dir,
            remaining=MAX_CANDIDATES - candidates_scanned,
            budget=budget,
            progress_callback=progress_callback,
            cancellation_requested=cancellation_requested,
            warnings=warnings,
        )
        if candidate_dirs is None:
            warnings.append(f"candidate_directory_unreadable:{run_root.name}")
            continue
        if candidate_limit_reached:
            truncated = True
            if budget.exhausted:
                warnings.append(f"directory_entry_limit_reached:{MAX_DIRECTORY_ENTRIES}")
            else:
                warnings.append(f"candidate_limit_reached:{MAX_CANDIDATES}")
        for candidate_root in candidate_dirs:
            _check_cancelled(cancellation_requested)
            if candidates_scanned >= MAX_CANDIDATES:
                truncated = True
                if f"candidate_limit_reached:{MAX_CANDIDATES}" not in warnings:
                    warnings.append(f"candidate_limit_reached:{MAX_CANDIDATES}")
                break
            candidates_scanned += 1
            _emit_progress(
                progress_callback,
                stage="read_candidate_summary",
                completed=candidates_scanned,
                total=MAX_CANDIDATES,
                path=candidate_root,
            )
            entries.append(
                _list_entry(candidate_root, learning_root=learning_root)
            )
        if truncated and candidates_scanned >= MAX_CANDIDATES:
            break

    entries.sort(key=lambda entry: (entry.candidate_id or "", entry.candidate_root))
    has_read_errors = any("unreadable" in warning or "unsafe" in warning for warning in warnings)
    status = (
        "incomplete"
        if has_read_errors
        else "truncated"
        if truncated
        else "complete"
        if entries
        else "empty"
    )
    next_step = (
        "清冊有路徑無法讀取；修復 learning root 權限或候選目錄後重試。"
        if has_read_errors
        else "清單受固定掃描預算限制；可縮小 learning root 範圍後重新整理。"
        if truncated
        else "選取候選後執行完整 metadata/artifact/lineage 讀回；只有讀回完成才會產生可確認的 pins。"
        if entries
        else "找不到候選；完成一次具完整 lineage 的個人校準訓練後，再重新整理。"
    )
    return PersonalCandidateInventorySnapshotV1(
        learning_root=str(learning_root),
        status=status,
        entries=tuple(entries),
        run_roots_scanned=len(run_roots),
        candidates_scanned=candidates_scanned,
        truncated=truncated,
        warnings=tuple(warnings),
        next_step=next_step,
    )


def inspect_personal_calibration_candidate(
    *,
    candidate_root: str | Path,
    data_root: str | Path | None = None,
    explicit_output_root: str | Path | None = None,
    source_database_path: str | Path | None = None,
    personal_use_policy: Any | None = None,
    progress_callback: ProgressCallback | None = None,
    cancellation_requested: CancellationCheck | None = None,
) -> PersonalCandidateInventoryEntryV1:
    """檢查候選並重驗明示保存的 V2 來源信任；不反序列化模型。"""

    return _inspect_personal_calibration_candidate(
        candidate_root=candidate_root,
        data_root=data_root,
        explicit_output_root=explicit_output_root,
        source_database_path=source_database_path,
        personal_use_policy=personal_use_policy,
        progress_callback=progress_callback,
        cancellation_requested=cancellation_requested,
        allow_unconfirmed_proposal=False,
        proof_evidence_out=None,
    )


def inspect_personal_source_time_binding(
    *,
    candidate_root: str | Path,
    source_database_path: str | Path,
    data_root: str | Path | None = None,
    explicit_output_root: str | Path | None = None,
    progress_callback: ProgressCallback | None = None,
    cancellation_requested: CancellationCheck | None = None,
) -> Any:
    """建立供使用者確認的來源綁定提案；本函式不保存信任選擇。"""

    from app_module.recommendation.personal_use_policy import (
        PersonalSourceFileIdentityV1,
        PersonalSourceReplayScopeV1,
        PersonalSourceTimeBindingProposalV1,
    )

    proof_evidence: dict[str, Any] = {}
    entry = _inspect_personal_calibration_candidate(
        candidate_root=candidate_root,
        data_root=data_root,
        explicit_output_root=explicit_output_root,
        source_database_path=source_database_path,
        personal_use_policy=None,
        progress_callback=progress_callback,
        cancellation_requested=cancellation_requested,
        allow_unconfirmed_proposal=True,
        proof_evidence_out=proof_evidence,
    )
    if entry.candidate is None or not proof_evidence:
        raise PersonalCandidateInventoryError(
            f"來源綁定提案不可用:{entry.reason_code}"
        )
    return PersonalSourceTimeBindingProposalV1(
        source_database_path=str(proof_evidence["source_database_path"]),
        file_identity=PersonalSourceFileIdentityV1(
            device=int(proof_evidence["file_identity"]["device"]),
            inode=int(proof_evidence["file_identity"]["inode"]),
        ),
        source_database_size_bytes=int(proof_evidence["source_database_size_bytes"]),
        source_slice_sha256=str(proof_evidence["source_slice_sha256"]),
        candidate=entry.candidate,
        replay_scope=PersonalSourceReplayScopeV1(
            dataset_ids=tuple(proof_evidence["dataset_ids"]),
            decision_dates=tuple(proof_evidence["decision_dates"]),
            symbols=tuple(proof_evidence["symbols"]),
            sample_count=int(proof_evidence["sample_count"]),
        ),
    )


def _inspect_personal_calibration_candidate(
    *,
    candidate_root: str | Path,
    data_root: str | Path | None,
    explicit_output_root: str | Path | None,
    source_database_path: str | Path | None,
    personal_use_policy: Any | None,
    progress_callback: ProgressCallback | None,
    cancellation_requested: CancellationCheck | None,
    allow_unconfirmed_proposal: bool,
    proof_evidence_out: dict[str, Any] | None,
) -> PersonalCandidateInventoryEntryV1:
    """共用 metadata/replay 驗證；只有 preview 或匹配 V2 trust 才回傳 pins。"""

    learning_root = _learning_root(data_root, explicit_output_root)
    requested_root = Path(candidate_root)
    try:
        root = _validated_candidate_root(requested_root, learning_root)
        candidate_bytes = _read_bounded_file(
            root / "candidate.json",
            root=learning_root,
            maximum_bytes=MAX_CANDIDATE_JSON_BYTES,
        )
        candidate_payload = _json_mapping(candidate_bytes, "candidate.json")
        summary = _entry_from_payload(root, candidate_payload)
        if summary.status == "legacy_unproven":
            return summary
        if summary.status == "unavailable":
            return summary

        _check_cancelled(cancellation_requested)
        manifest_bytes = _read_bounded_file(
            root / "manifest.json",
            root=learning_root,
            maximum_bytes=MAX_MANIFEST_JSON_BYTES,
        )
        manifest_payload = _json_mapping(manifest_bytes, "manifest.json")
        manifest = _parse_manifest(manifest_payload)
        _validate_candidate_manifest_binding(candidate_payload, manifest)

        artifact_path = root / manifest.artifact_filename
        artifact_hash = _hash_bounded_file(
            artifact_path,
            root=learning_root,
            maximum_bytes=MAX_ARTIFACT_BYTES,
            progress_callback=progress_callback,
            cancellation_requested=cancellation_requested,
        )
        if artifact_hash != manifest.artifact_hash:
            return _unavailable_entry(
                root,
                candidate_payload,
                reason_code="artifact_hash_mismatch",
                next_step="候選 artifact bytes 與 manifest 不符；請重新產生候選，不要手動修補 hash。",
            )

        lineage_status, lineage_payload = _validate_lineage_snapshot(
            root=root,
            learning_root=learning_root,
            candidate_payload=candidate_payload,
            cancellation_requested=cancellation_requested,
            progress_callback=progress_callback,
        )
        if lineage_status == "legacy_unproven":
            return _unavailable_entry(
                root,
                candidate_payload,
                reason_code="training_lineage_missing",
                status="legacy_unproven",
                next_step="此舊候選沒有可驗證 training lineage；請用目前 runner 重新訓練並讀回完整 lineage。",
            )
        assert lineage_payload is not None

        context = lineage_payload.get("training_context")
        if not isinstance(context, Mapping):
            raise PersonalCandidateInventoryError("training lineage context 無效")
        semantics = context.get("semantics")
        eligible = context.get("decision_time_eligible")
        if semantics != candidate_payload.get("training_semantics") or eligible is not candidate_payload.get(
            "decision_time_eligible"
        ):
            raise PersonalCandidateInventoryError("候選與 training lineage 時間契約不一致")
        candidate_fit_cutoff = candidate_payload.get("training_as_of")
        lineage_cutoff = lineage_payload.get("training_as_of")
        if (
            type(candidate_fit_cutoff) is not str
            or not _is_iso_day(candidate_fit_cutoff)
            or type(lineage_cutoff) is not str
            or not _is_iso_day(lineage_cutoff)
        ):
            raise PersonalCandidateInventoryError("候選或 training lineage cutoff 日期無效")
        if "training_cutoff" in candidate_payload:
            candidate_training_cutoff = candidate_payload.get("training_cutoff")
            if (
                type(candidate_training_cutoff) is not str
                or not _is_iso_day(candidate_training_cutoff)
                or candidate_training_cutoff != lineage_cutoff
            ):
                raise PersonalCandidateInventoryError(
                    "候選 training_cutoff 與 training lineage cutoff 不一致"
                )
            if date.fromisoformat(candidate_fit_cutoff) > date.fromisoformat(
                candidate_training_cutoff
            ):
                raise PersonalCandidateInventoryError(
                    "候選模型 fit cutoff 晚於 training lineage label-availability cutoff"
                )
        elif candidate_fit_cutoff != lineage_cutoff:
            # 舊版候選沒有獨立記錄完整輸入 cutoff；只接受舊有相等形狀。
            raise PersonalCandidateInventoryError("舊候選與 training lineage 截止日不一致")
        if semantics != "decision_time" or eligible is not True:
            return _unavailable_entry(
                root,
                candidate_payload,
                reason_code="training_not_decision_time_eligible",
                status="historical_research_only",
                next_step="此候選僅供歷史研究；請以不晚於訓練決策日可取得的資料重新產生候選。",
            )
        if candidate_payload.get("training_data_eligible") is not True:
            return _unavailable_entry(
                root,
                candidate_payload,
                reason_code="training_data_not_eligible",
                next_step="候選訓練資料未通過既有資料 eligibility；請修復資料來源後重跑訓練。",
            )
        if source_database_path is None:
            return _unavailable_entry(
                root,
                candidate_payload,
                status="historical_research_only",
                reason_code="independent_source_time_authority_missing",
                next_step=(
                    "個人模型需要使用者明示信任的資料庫來源；先指定資料庫並檢查來源綁定，"
                    "再確認為研究用途。"
                ),
            )
        proof_evidence: dict[str, Any] = {}
        proof_error = verify_personal_training_source_time_proof(
            lineage_payload=lineage_payload,
            learning_root=learning_root,
            data_root=data_root,
            source_database_path=source_database_path,
            evidence_out=proof_evidence,
        )
        if proof_error is not None:
            return _unavailable_entry(
                root,
                candidate_payload,
                status="historical_research_only",
                reason_code=proof_error,
                next_step="目前資料庫與訓練來源無法完成有界一致性驗證；請確認來源路徑、資料與訓練 lineage。",
            )
        freeze_hash = _candidate_freeze_hash(candidate_payload, manifest)
        candidate_ref = PersonalCalibrationCandidateV1(
            candidate_id=str(candidate_payload["candidate_id"]),
            candidate_root=str(root.resolve(strict=True)),
            candidate_json_sha256=_sha256_bytes(candidate_bytes),
            candidate_manifest_hash=str(manifest.manifest_hash),
            candidate_artifact_hash=str(manifest.artifact_hash),
            candidate_freeze_hash=freeze_hash,
            dataset_hash=str(candidate_payload["dataset_hash"]),
        )
        if proof_evidence_out is not None:
            proof_evidence_out.clear()
            proof_evidence_out.update(proof_evidence)
        if allow_unconfirmed_proposal:
            return _entry_from_payload(
                root,
                candidate_payload,
                status="source_time_binding_proposal_ready",
                reason_code="user_confirmation_required",
                next_step="檢查來源資料庫與訓練範圍，明確確認此研究用途後再保存個人政策。",
                candidate=candidate_ref,
                source_time_basis="user_declared_source_time",
                research_only=True,
                official_historical_pit_verified=False,
            )
        if not _saved_v2_source_binding_matches(
            personal_use_policy,
            candidate_ref=candidate_ref,
            proof_evidence=proof_evidence,
        ):
            return _unavailable_entry(
                root,
                candidate_payload,
                status="historical_research_only",
                reason_code=_v2_source_binding_failure_reason(personal_use_policy),
                next_step="目前政策未保存或不再符合這個資料庫與候選來源綁定；請重新檢查來源並明確確認。",
            )
        return _entry_from_payload(
            root,
            candidate_payload,
            status="metadata_pinned_pending_runtime_validation",
            reason_code="user_declared_source_time_research_only",
            next_step="來源與候選可供 consumer 再做 runtime 硬驗；仍是個人研究模式，不代表官方歷史 PIT。",
            candidate=candidate_ref,
            source_time_basis="user_declared_source_time",
            research_only=True,
            official_historical_pit_verified=False,
        )
    except PersonalCandidateInventoryCancelled:
        raise
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        return _unavailable_entry(
            requested_root,
            {},
            reason_code=_reason_code(exc),
            next_step="候選讀回或契約驗證失敗；請重新產生候選或檢查 learning root 權限與檔案完整性。",
        )


def _saved_v2_source_binding_matches(
    policy: Any | None,
    *,
    candidate_ref: PersonalCalibrationCandidateV1,
    proof_evidence: Mapping[str, Any],
) -> bool:
    if type(policy) is not RecommendationPersonalUsePolicyV2:
        return False
    try:
        storage_path = policy.storage_path
        if (
            policy.version != 2
            or policy.to_dict().get("schema_version")
            != "recommendation-personal-use-policy.v2"
            or getattr(policy, "mode", None) != "personal_calibrated_probability"
            or storage_path is None
            or type(getattr(policy, "storage_bytes", None)) is not bytes
        ):
            return False
        validated = policy.validate_snapshot()
        if validated.to_dict() != policy.to_dict():
            return False
        on_disk = load_personal_use_policy_snapshot(storage_path)
        if (
            type(on_disk) is not RecommendationPersonalUsePolicyV2
            or on_disk.storage_bytes != policy.storage_bytes
            or on_disk.to_dict() != policy.to_dict()
        ):
            return False
        trust = getattr(policy, "source_time_trust", None)
        candidate = getattr(policy, "candidate", None)
        if trust is None or candidate is None:
            return False
        if candidate.to_dict() != candidate_ref.to_dict():
            return False
        if trust.candidate.to_dict() != candidate_ref.to_dict():
            return False
        source_path = str(proof_evidence["source_database_path"])
        source_identity = proof_evidence["file_identity"]
        replay_scope = proof_evidence["replay_scope"]
        trust_identity = trust.file_identity
        trust_scope = trust.replay_scope
        return (
            trust.schema_version == "personal-user-declared-source-time-trust.v1"
            and trust.basis == "user_declared_source_time"
            and trust.confirmed_at == policy.confirmed_at
            and trust.source_database_path == source_path
            and trust_identity.device == source_identity["device"]
            and trust_identity.inode == source_identity["inode"]
            and trust.source_slice_sha256 == proof_evidence["source_slice_sha256"]
            and tuple(trust_scope.dataset_ids) == tuple(replay_scope["dataset_ids"])
            and tuple(trust_scope.decision_dates) == tuple(replay_scope["decision_dates"])
            and tuple(trust_scope.symbols) == tuple(replay_scope["symbols"])
            and trust_scope.sample_count == replay_scope["sample_count"]
            and trust.research_only is True
            and trust.official_historical_pit_verified is False
        )
    except (AttributeError, TypeError, ValueError):
        return False


def _v2_source_binding_failure_reason(policy: Any | None) -> str:
    if policy is None:
        return "independent_source_time_authority_missing"
    if (
        type(policy) is not RecommendationPersonalUsePolicyV2
        or policy.to_dict().get("schema_version")
        != "recommendation-personal-use-policy.v2"
    ):
        return "independent_source_time_authority_missing"
    return "source_time_binding_mismatch"


def _learning_root(
    data_root: str | Path | None,
    explicit_output_root: str | Path | None,
) -> Path:
    return resolve_recommendation_learning_paths(
        data_root=data_root,
        explicit_output_root=explicit_output_root,
    ).learning_root.resolve()


def _discover_run_candidate_roots(
    runs_root: Path,
    *,
    budget: _DirectoryEntryBudget,
    progress_callback: ProgressCallback | None,
    cancellation_requested: CancellationCheck | None,
) -> tuple[list[tuple[Path, Path]], bool, list[str]]:
    found: list[tuple[Path, Path]] = []
    truncated = False
    warnings: list[str] = []
    try:
        run_entries = os.scandir(runs_root)
    except OSError:
        return [], False, ["runs_directory_unreadable"]
    with run_entries:
        while True:
            try:
                run_entry = next(run_entries)
            except StopIteration:
                break
            except OSError:
                warnings.append("runs_directory_unreadable")
                break
            _check_cancelled(cancellation_requested)
            if not budget.consume():
                truncated = True
                warnings.append(f"directory_entry_limit_reached:{MAX_DIRECTORY_ENTRIES}")
                break
            _emit_progress(
                progress_callback,
                stage="discover_run_roots",
                completed=budget.observed,
                total=budget.limit,
                path=Path(run_entry.path),
            )
            if run_entry.is_symlink():
                warnings.append(f"unsafe_run_root_skipped:{run_entry.name}")
                continue
            try:
                if not run_entry.is_dir(follow_symlinks=False) or not _is_iso_day(run_entry.name):
                    continue
            except OSError:
                warnings.append("run_root_entry_unreadable")
                continue
            run_day = Path(run_entry.path)
            if not _is_safe_directory(run_day):
                warnings.append(f"unsafe_run_root_skipped:{run_entry.name}")
                continue
            direct_candidates = run_day / "candidates"
            direct_state = _directory_state(direct_candidates)
            if direct_state == "directory":
                found.append((run_day, direct_candidates))
                if len(found) > MAX_RUN_ROOTS:
                    truncated = True
                    warnings.append(f"run_root_limit_reached:{MAX_RUN_ROOTS}")
                    break
            elif direct_state == "unreadable":
                warnings.append(f"candidate_directory_unreadable:{run_day.name}")
            elif direct_state == "unsafe":
                warnings.append(f"unsafe_candidate_directory_skipped:{run_day.name}")
            try:
                scope_entries = os.scandir(run_day)
            except OSError:
                warnings.append(f"run_day_unreadable:{run_day.name}")
                continue
            with scope_entries:
                while True:
                    try:
                        scope_entry = next(scope_entries)
                    except StopIteration:
                        break
                    except OSError:
                        warnings.append(f"run_day_unreadable:{run_day.name}")
                        break
                    _check_cancelled(cancellation_requested)
                    if not budget.consume():
                        truncated = True
                        warnings.append(f"directory_entry_limit_reached:{MAX_DIRECTORY_ENTRIES}")
                        break
                    _emit_progress(
                        progress_callback,
                        stage="discover_run_scope",
                        completed=budget.observed,
                        total=budget.limit,
                        path=Path(scope_entry.path),
                    )
                    if scope_entry.is_symlink():
                        warnings.append(f"unsafe_run_scope_skipped:{scope_entry.name}")
                        continue
                    if scope_entry.name == "candidates":
                        continue
                    try:
                        if not scope_entry.is_dir(follow_symlinks=False):
                            continue
                    except OSError:
                        warnings.append(f"run_scope_entry_unreadable:{scope_entry.name}")
                        continue
                    scope_root = Path(scope_entry.path)
                    if not _is_safe_directory(scope_root):
                        warnings.append(f"unsafe_run_scope_skipped:{scope_entry.name}")
                        continue
                    scoped_candidates = scope_root / "candidates"
                    scope_candidates_state = _directory_state(scoped_candidates)
                    if scope_candidates_state == "unreadable":
                        warnings.append(f"candidate_directory_unreadable:{scope_entry.name}")
                        continue
                    if scope_candidates_state == "unsafe":
                        warnings.append(f"unsafe_candidate_directory_skipped:{scope_entry.name}")
                        continue
                    if scope_candidates_state != "directory":
                        continue
                    found.append((scope_root, scoped_candidates))
                    if len(found) > MAX_RUN_ROOTS:
                        truncated = True
                        warnings.append(f"run_root_limit_reached:{MAX_RUN_ROOTS}")
                        break
                if truncated:
                    break
            if truncated:
                break
    if truncated:
        found = found[:MAX_RUN_ROOTS]
    return found, truncated, warnings


def _bounded_child_directories(
    parent: Path,
    *,
    remaining: int,
    budget: _DirectoryEntryBudget,
    progress_callback: ProgressCallback | None,
    cancellation_requested: CancellationCheck | None,
    warnings: list[str],
) -> tuple[list[Path] | None, bool]:
    limit = max(0, remaining)
    children: list[Path] = []
    try:
        with os.scandir(parent) as iterator:
            for item in iterator:
                _check_cancelled(cancellation_requested)
                if not budget.consume():
                    return sorted(children), True
                _emit_progress(
                    progress_callback,
                    stage="discover_candidates",
                    completed=budget.observed,
                    total=budget.limit,
                    path=Path(item.path),
                )
                if item.is_symlink():
                    warnings.append(f"unsafe_candidate_directory_skipped:{item.name}")
                    continue
                if not item.is_dir(follow_symlinks=False):
                    continue
                children.append(Path(item.path))
                if len(children) > limit:
                    return sorted(children[:limit]), True
    except OSError:
        return None, False
    return sorted(children), False


def _list_entry(candidate_root: Path, *, learning_root: Path) -> PersonalCandidateInventoryEntryV1:
    try:
        root = _validated_candidate_root(candidate_root, learning_root)
        payload = _json_mapping(
            _read_bounded_file(
                root / "candidate.json",
                root=learning_root,
                maximum_bytes=MAX_CANDIDATE_JSON_BYTES,
            ),
            "candidate.json",
        )
        entry = _entry_from_payload(root, payload)
        if entry.status == "metadata_unverified":
            return _entry_from_payload(
                root,
                payload,
                status="metadata_unverified",
                reason_code="selection_requires_full_readback",
                next_step="選取候選後完整檢查 manifest、artifact hash 與 training lineage。",
            )
        return entry
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        return _unavailable_entry(
            candidate_root,
            {},
            reason_code=_reason_code(exc),
            next_step="候選摘要不可讀；檢查檔案是否完整，或重新產生此候選。",
        )


def _entry_from_payload(
    candidate_root: Path,
    payload: Mapping[str, Any],
    *,
    status: str | None = None,
    reason_code: str | None = None,
    next_step: str | None = None,
    candidate: PersonalCalibrationCandidateV1 | None = None,
    source_time_basis: str | None = None,
    research_only: bool | None = None,
    official_historical_pit_verified: bool | None = None,
) -> PersonalCandidateInventoryEntryV1:
    candidate_id_value = payload.get("candidate_id")
    candidate_id = candidate_id_value if type(candidate_id_value) is str else None
    if candidate_id is None or candidate_id != candidate_root.name:
        return _unavailable_entry(
            candidate_root,
            payload,
            reason_code="candidate_identity_mismatch",
            next_step="候選目錄名稱與 metadata identity 不一致；請重新產生候選。",
        )
    if payload.get("schema_version") != "recommendation-calibration-candidate.v1":
        return _unavailable_entry(
            candidate_root,
            payload,
            reason_code="candidate_schema_unsupported",
            next_step="候選 schema 版本不受支援；請用目前 training runner 重新產生。",
        )
    lineage_hash_present = "training_lineage_manifest_hash" in payload
    lineage_path_present = "training_lineage_manifest_path" in payload
    lineage_hash = payload.get("training_lineage_manifest_hash")
    lineage_path = payload.get("training_lineage_manifest_path")
    if not lineage_hash_present and not lineage_path_present:
        selected_status = "legacy_unproven"
        selected_reason = "training_lineage_missing"
        selected_next = "此舊候選沒有 training lineage；請用目前 runner 重跑並保存完整 lineage。"
    elif (
        not lineage_hash_present
        or not lineage_path_present
        or not _is_sha256(lineage_hash)
        or type(lineage_path) is not str
        or not lineage_path.strip()
    ):
        selected_status = "unavailable"
        selected_reason = "training_lineage_declaration_invalid"
        selected_next = "候選 lineage 宣告不完整；請重新產生候選。"
    else:
        selected_status = "metadata_unverified"
        selected_reason = "metadata_not_yet_read_back"
        selected_next = "選取候選後完整檢查 artifact 與 lineage。"
    blockers = payload.get("candidate_blockers")
    blocker_values = (
        tuple(item for item in blockers if type(item) is str)
        if isinstance(blockers, list)
        else ()
    )
    return PersonalCandidateInventoryEntryV1(
        candidate_id=candidate_id,
        candidate_root=str(candidate_root),
        status=status or selected_status,
        reason_code=reason_code or selected_reason,
        display_label=candidate_id,
        candidate_frozen_at=_optional_text(payload.get("candidate_frozen_at")),
        training_as_of=_optional_text(payload.get("training_as_of")),
        training_semantics=_optional_text(payload.get("training_semantics")),
        decision_time_eligible=(
            payload.get("decision_time_eligible")
            if type(payload.get("decision_time_eligible")) is bool
            else None
        ),
        dataset_id=_optional_text(payload.get("dataset_id")),
        training_row_count=_optional_int(payload.get("training_row_count")),
        calibration_sample_count=_optional_int(payload.get("calibration_sample_count")),
        calibration_gap_bp=_optional_int(payload.get("calibration_gap_bp")),
        candidate_blockers=blocker_values,
        next_step=next_step or selected_next,
        candidate=candidate,
        source_time_basis=source_time_basis,
        research_only=research_only,
        official_historical_pit_verified=official_historical_pit_verified,
    )


def verify_personal_training_source_time_proof(
    *,
    lineage_payload: Mapping[str, Any],
    learning_root: str | Path,
    data_root: str | Path | None,
    source_database_path: str | Path | None = None,
    evidence_out: dict[str, Any] | None = None,
) -> str | None:
    """核對有界 replay 與明示或設定 SQLite 內容一致；不代表官方來源權威。"""

    try:
        return _verify_personal_training_source_time_proof(
            lineage_payload=lineage_payload,
            learning_root=Path(learning_root),
            data_root=data_root,
            source_database_path=source_database_path,
            evidence_out=evidence_out,
        )
    except PersonalCandidateInventoryCancelled:
        raise
    except (
        OSError,
        RuntimeError,
        sqlite3.Error,
        TypeError,
        ValueError,
        KeyError,
        OverflowError,
    ) as exc:
        return _source_proof_failure_code(exc)


def learning_root_for_personal_candidate(candidate_root: str | Path) -> Path:
    """從固定候選目錄形狀取 learning root，不接受任意相鄰資料夾。"""

    root = Path(candidate_root)
    _reject_reparse_components(root)
    resolved_root = root.resolve(strict=True)
    for parent in resolved_root.parents:
        if parent.name != "recommendation_learning":
            continue
        try:
            relative = resolved_root.relative_to(parent).parts
        except ValueError:
            continue
        if (
            len(relative) in {4, 5}
            and relative[0] == "runs"
            and relative[-2] == "candidates"
            and all(relative)
        ):
            return parent
    raise PersonalCandidateInventoryError("candidate_root 不符合 learning root 固定形狀")


def _verify_personal_training_source_time_proof(
    *,
    lineage_payload: Mapping[str, Any],
    learning_root: Path,
    data_root: str | Path | None,
    source_database_path: str | Path | None = None,
    evidence_out: dict[str, Any] | None = None,
) -> str | None:
    from datetime import date

    from data_module.ml_historical_snapshot_provider import MLHistoricalSnapshotProvider
    from ml_module.recommendation_historical_replay import (
        RecommendationHistoricalReplayConfig,
        RecommendationHistoricalReplayService,
    )

    if not isinstance(lineage_payload, Mapping):
        return "training_source_time_proof_lineage_invalid"
    replay_references = lineage_payload.get("replay_manifests")
    if not isinstance(replay_references, list) or not replay_references:
        return "training_source_time_proof_missing"
    if len(replay_references) > MAX_SOURCE_PROOF_MANIFESTS:
        return "training_source_time_proof_budget_exceeded"

    merged_samples = lineage_payload.get("merged_samples")
    if not isinstance(merged_samples, list) or len(merged_samples) > MAX_SOURCE_PROOF_SAMPLES:
        return "training_source_time_proof_training_rows_invalid"
    merged_by_id: dict[str, Mapping[str, Any]] = {}
    for sample in merged_samples:
        if not isinstance(sample, Mapping):
            return "training_source_time_proof_training_rows_invalid"
        row_id = sample.get("row_id")
        if type(row_id) is not str or not row_id or row_id in merged_by_id:
            return "training_source_time_proof_training_rows_invalid"
        merged_by_id[row_id] = sample

    normalized_learning_root = learning_root.resolve(strict=True)
    if normalized_learning_root.name != "recommendation_learning":
        return "training_source_time_proof_learning_root_invalid"
    if evidence_out is not None:
        evidence_out.clear()
    if source_database_path is None:
        configured_paths = resolve_recommendation_learning_paths(data_root=data_root)
        source_database = configured_paths.data_root / "sqlite" / "twstock.db"
    else:
        source_database = Path(source_database_path)
        if not source_database.is_absolute():
            return "training_source_time_proof_database_path_invalid"
    _reject_reparse_components(source_database)
    source_database = source_database.resolve(strict=True)
    database_before = _regular_file_stat(source_database)
    if (
        type(database_before.st_dev) is not int
        or type(database_before.st_ino) is not int
        or database_before.st_dev < 0
        or database_before.st_ino <= 0
    ):
        return "training_source_time_proof_file_identity_unavailable"
    if database_before.st_size > MAX_SOURCE_PROOF_DATABASE_BYTES:
        return "training_source_time_proof_database_budget_exceeded"

    total_manifest_bytes = 0
    total_decision_dates = 0
    total_samples = 0
    total_source_contract_rows = 0
    all_symbols: set[str] = set()
    all_decision_dates: set[str] = set()
    all_dataset_ids: set[str] = set()
    source_slice_material: list[dict[str, Any]] = []
    verified_replay_rows: dict[str, Mapping[str, Any]] = {}
    provider = MLHistoricalSnapshotProvider(source_database)

    for reference in replay_references:
        if not isinstance(reference, Mapping):
            return "training_source_time_proof_reference_invalid"
        dataset_id = reference.get("dataset_id")
        if type(dataset_id) is not str or not _DATASET_ID_RE.fullmatch(dataset_id):
            return "training_source_time_proof_dataset_identity_invalid"
        manifest_path_text = reference.get("path")
        if type(manifest_path_text) is not str or not Path(manifest_path_text).is_absolute():
            return "training_source_time_proof_manifest_path_invalid"
        manifest_path = Path(manifest_path_text)
        _reject_reparse_components(manifest_path)
        expected_path = normalized_learning_root / "datasets" / dataset_id / "dataset.json"
        resolved_manifest_path = manifest_path.resolve(strict=True)
        if resolved_manifest_path != expected_path.resolve(strict=True):
            return "training_source_time_proof_manifest_path_invalid"
        raw = _read_bounded_file(
            resolved_manifest_path,
            root=normalized_learning_root,
            maximum_bytes=MAX_REPLAY_MANIFEST_JSON_BYTES,
        )
        total_manifest_bytes += len(raw)
        if total_manifest_bytes > MAX_REPLAY_MANIFEST_JSON_BYTES * MAX_SOURCE_PROOF_MANIFESTS:
            return "training_source_time_proof_budget_exceeded"
        if reference.get("file_hash") != _sha256_bytes(raw):
            return "training_source_time_proof_manifest_hash_mismatch"
        manifest = _json_mapping(raw, "dataset.json")
        if manifest.get("schema_version") != "recommendation-historical-replay-dataset.v1":
            return "training_source_time_proof_manifest_schema_invalid"
        if manifest.get("dataset_id") != dataset_id:
            return "training_source_time_proof_dataset_identity_invalid"
        if manifest.get("dataset_hash") != reference.get("dataset_hash"):
            return "training_source_time_proof_dataset_hash_mismatch"
        raw_samples = manifest.get("samples")
        decision_dates = manifest.get("decision_dates")
        coverage = manifest.get("coverage")
        disclosures = manifest.get("source_disclosures")
        if (
            not isinstance(raw_samples, list)
            or not isinstance(decision_dates, list)
            or not isinstance(coverage, Mapping)
            or not isinstance(disclosures, Mapping)
        ):
            return "training_source_time_proof_manifest_shape_invalid"
        if (
            type(reference.get("sample_count")) is not int
            or reference.get("sample_count") != len(raw_samples)
            or len(raw_samples) > MAX_SOURCE_PROOF_SAMPLES
            or type(manifest.get("sample_count")) is not int
            or manifest.get("sample_count") != len(raw_samples)
            or reference.get("training_data_eligible") is not True
            or manifest.get("training_data_eligible") is not True
        ):
            return "training_source_time_proof_manifest_rows_invalid"
        row_ids = sorted(
            str(sample.get("row_id"))
            for sample in raw_samples
            if isinstance(sample, Mapping) and type(sample.get("row_id")) is str
        )
        if (
            len(row_ids) != len(raw_samples)
            or len(set(row_ids)) != len(row_ids)
            or reference.get("row_ids") != row_ids
        ):
            return "training_source_time_proof_manifest_rows_invalid"
        if reference.get("decision_dates") != decision_dates:
            return "training_source_time_proof_decision_dates_mismatch"
        if (
            not decision_dates
            or len(decision_dates) > MAX_SOURCE_PROOF_DECISION_DATES
            or any(type(item) is not str for item in decision_dates)
            or decision_dates != sorted(set(decision_dates))
        ):
            return "training_source_time_proof_budget_exceeded"

        contract_summary = disclosures.get("source_contract")
        cost_disclosure = disclosures.get("cost")
        if not isinstance(contract_summary, Mapping) or not isinstance(cost_disclosure, Mapping):
            return "training_source_time_config_not_reconstructable"
        symbols = coverage.get("requested_symbols")
        if (
            not isinstance(symbols, list)
            or not symbols
            or any(type(symbol) is not str or not symbol.strip() for symbol in symbols)
            or len(symbols) > MAX_SOURCE_PROOF_SYMBOLS
            or len(set(symbols)) != len(symbols)
        ):
            return "training_source_time_proof_budget_exceeded"
        all_symbols.update(symbols)
        if len(all_symbols) > MAX_SOURCE_PROOF_SYMBOLS:
            return "training_source_time_proof_budget_exceeded"
        maximum_dates = coverage.get("max_decision_dates")
        if type(maximum_dates) is not int or not 1 <= maximum_dates <= MAX_SOURCE_PROOF_DECISION_DATES:
            return "training_source_time_proof_budget_exceeded"
        date_keys = (
            contract_summary.get("history_start_date"),
            contract_summary.get("replay_start_date"),
            contract_summary.get("replay_end_date"),
        )
        if any(type(item) is not str or not _is_iso_day(item) for item in date_keys):
            return "training_source_time_proof_config_invalid"
        history_start, replay_start, replay_end = (
            date.fromisoformat(str(item)) for item in date_keys
        )
        if (
            history_start > replay_start
            or replay_start > replay_end
            or (replay_end - history_start).days > MAX_SOURCE_PROOF_HISTORY_DAYS
        ):
            return "training_source_time_proof_budget_exceeded"
        total_decision_dates += len(decision_dates)
        total_samples += len(raw_samples)
        all_decision_dates.update(str(item) for item in decision_dates)
        all_dataset_ids.add(dataset_id)
        if (
            total_decision_dates > MAX_SOURCE_PROOF_DECISION_DATES
            or total_samples > MAX_SOURCE_PROOF_SAMPLES
        ):
            return "training_source_time_proof_budget_exceeded"

        fixed_cost = cost_disclosure.get("fixed_round_trip_cost_bp")
        if (
            type(fixed_cost) is not int
            or fixed_cost < 0
            or cost_disclosure.get("cost_basis") != "fixed_round_trip_bp"
            or any(
                not isinstance(sample, Mapping)
                or sample.get("fixed_round_trip_cost_bp") != fixed_cost
                for sample in raw_samples
            )
        ):
            return "training_source_time_config_not_reconstructable"
        declared_cost_hash = coverage.get("cost_scenario_hash")
        declared_cost_id = coverage.get("cost_scenario_id")
        if (
            type(declared_cost_hash) is not str
            or _SHA256_RE.fullmatch(declared_cost_hash) is None
            or declared_cost_id != "legacy-fixed-round-trip-bp"
            or cost_disclosure.get("cost_scenario_hash") != declared_cost_hash
            or cost_disclosure.get("cost_scenario_id") != declared_cost_id
        ):
            return "training_source_time_config_not_reconstructable"
        rule_probabilities = {
            sample.get("rule_probability_bp")
            for sample in raw_samples
            if isinstance(sample, Mapping)
        }
        rule_baselines = {
            sample.get("rule_baseline_id")
            for sample in raw_samples
            if isinstance(sample, Mapping)
        }
        if (
            len(rule_probabilities) != 1
            or type(next(iter(rule_probabilities), None)) is not int
            or len(rule_baselines) != 1
            or type(next(iter(rule_baselines), None)) is not str
            or coverage.get("selection_policy") not in {
                "chronological_first_eligible_date",
                "latest_eligible_dates",
                "time_stratified_eligible_dates",
            }
        ):
            return "training_source_time_config_not_reconstructable"
        config_values: dict[str, Any] = {
            "history_start_date": history_start.isoformat(),
            "replay_start_date": replay_start.isoformat(),
            "replay_end_date": replay_end.isoformat(),
            "symbols": tuple(symbols),
            "fixed_round_trip_cost_bp": fixed_cost,
            "max_decision_dates": maximum_dates,
            "industry_index_name_by_symbol": {},
            "rule_probability_bp": next(iter(rule_probabilities)),
            "rule_baseline_id": next(iter(rule_baselines)),
            "selection_policy": coverage["selection_policy"],
        }
        try:
            replay_config = RecommendationHistoricalReplayConfig(**config_values)
        except (TypeError, ValueError) as exc:
            raise PersonalCandidateInventoryError("training_source_time_proof_config_invalid") from exc
        scenario = replay_config.cost_scenario
        if declared_cost_hash is not None and getattr(scenario, "scenario_hash", None) != declared_cost_hash:
            return "training_source_time_proof_cost_scenario_mismatch"

        total_source_contract_rows += _count_source_contract_rows(
            source_database,
            symbols=tuple(symbols),
        )
        if total_source_contract_rows > MAX_SOURCE_PROOF_CONTRACT_ROWS:
            return "training_source_time_proof_budget_exceeded"

        replayed = RecommendationHistoricalReplayService(provider).build(replay_config)
        technical = replayed.source_disclosures.get("technical")
        corporate = replayed.source_disclosures.get("corporate_actions")
        technical_contract = technical.get("source_contract") if isinstance(technical, Mapping) else None
        corporate_contract = corporate.get("source_contract") if isinstance(corporate, Mapping) else None
        if (
            replayed.training_data_eligible is not True
            or not isinstance(technical_contract, Mapping)
            or technical_contract.get("verified") is not True
            or technical_contract.get("source_id") != _TRUSTED_SOURCE_IDS["technical"]
            or not isinstance(corporate_contract, Mapping)
            or corporate_contract.get("verified") is not True
            or corporate_contract.get("source_id") != _TRUSTED_SOURCE_IDS["corporate_actions"]
            or replayed.lookahead_checks.get("feature_snapshot_rows_strictly_before_decision") is not True
            or replayed.lookahead_checks.get("feature_available_date_not_after_decision") is not True
            or replayed.lookahead_checks.get("technical_publication_time_verified") is not True
            or replayed.lookahead_checks.get("corporate_action_adjustment_verified") is not True
        ):
            return "training_source_time_contract_unverified"
        replay_projection = _personal_replay_source_slice_projection(
            replayed.to_dict()
        )
        manifest_projection = _personal_replay_source_slice_projection(manifest)
        if _canonical_json(replay_projection) != _canonical_json(manifest_projection):
            return "training_source_time_replay_mismatch"
        source_slice_material.append(
            {"dataset_id": dataset_id, "replay": replay_projection}
        )
        database_after = _regular_file_stat(source_database)
        _same_file_version(database_before, database_after)

        for replay_sample in raw_samples:
            if not isinstance(replay_sample, Mapping):
                return "training_source_time_proof_manifest_rows_invalid"
            row_id = replay_sample.get("row_id")
            if type(row_id) is not str or not row_id:
                return "training_source_time_proof_manifest_rows_invalid"
            prior_sample = verified_replay_rows.get(row_id)
            if prior_sample is not None and _canonical_json(prior_sample) != _canonical_json(replay_sample):
                return "training_source_time_training_rows_mismatch"
            verified_replay_rows[row_id] = replay_sample

    if not verified_replay_rows:
        return "training_source_time_training_rows_unbound"
    for row_id, merged_sample in merged_by_id.items():
        replay_sample = verified_replay_rows.get(row_id)
        if replay_sample is None:
            return "training_source_time_training_rows_unbound"
        if _canonical_json(merged_sample) != _canonical_json(replay_sample):
            return "training_source_time_training_rows_mismatch"
    if set(merged_by_id) != set(verified_replay_rows):
        return "training_source_time_training_rows_unbound"
    database_after = _regular_file_stat(source_database)
    _same_file_version(database_before, database_after)
    if evidence_out is not None:
        source_slice_material.sort(key=lambda item: str(item["dataset_id"]))
        evidence_out.update(
            {
                "source_database_path": str(source_database),
                "file_identity": {
                    "device": int(database_after.st_dev),
                    "inode": int(database_after.st_ino),
                },
                "source_database_size_bytes": int(database_after.st_size),
                "source_slice_sha256": _sha256_bytes(
                    _canonical_json(
                        {
                            "schema_version": "personal-source-replay-slice.v1",
                            "datasets": source_slice_material,
                        }
                    ).encode("utf-8")
                ),
                "dataset_ids": sorted(all_dataset_ids),
                "decision_dates": sorted(all_decision_dates),
                "symbols": sorted(all_symbols),
                "sample_count": len(verified_replay_rows),
                "replay_scope": {
                    "dataset_ids": sorted(all_dataset_ids),
                    "decision_dates": sorted(all_decision_dates),
                    "symbols": sorted(all_symbols),
                    "sample_count": len(verified_replay_rows),
                },
            }
        )
    return None


def _personal_replay_source_slice_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    """只正規化 user-declared V2 日更例外，保留逐筆重播與候選 pins。"""

    projection = dict(value)
    # 僅排除 3 個由全資料庫 source_fingerprints 推導的頂層識別欄位；
    # 原候選的 dataset/manifest/artifact/freeze 識別與雜湊另在外層逐一精確驗證。
    for key in ("dataset_id", "dataset_hash", "source_fingerprint"):
        projection.pop(key, None)
    # 個人來源綁定只重驗候選實際使用的有界 replay 切片。以下正規化限於
    # 3 個精確 nested paths × 4 個整庫衍生彙總欄位；截止日後日更可改變
    # 這些彙總，但不應改寫訓練窗。原始 replay manifest 與全域 oracle 不套用。
    # samples/row identities、decision dates、重播設定與 coverage 請求、成本、
    # available_at、source_id、verified、source_columns 及其餘欄位仍逐欄比較。
    aggregate_fields = (
        "content_digest",
        "content_row_count",
        "coverage_end",
        "evidence_hash",
    )
    # Replay 目前以三個明確 wire 位置重複輸出同一技術來源合約；只處理
    # 這三條已核對路徑，不遞迴搜尋相同欄名，避免擴大忽略範圍。
    aggregate_paths = (
        ("coverage", "source_contract", "technical"),
        ("source_disclosures", "source_contract", "technical"),
        ("source_disclosures", "technical", "source_contract"),
    )
    for path in aggregate_paths:
        parent: dict[str, Any] = projection
        valid_path = True
        for key in path[:-1]:
            child = parent.get(key)
            if not isinstance(child, Mapping):
                valid_path = False
                break
            detached_child = dict(child)
            parent[key] = detached_child
            parent = detached_child
        if not valid_path:
            continue
        technical_value = parent.get(path[-1])
        if not isinstance(technical_value, Mapping):
            continue
        technical = dict(technical_value)
        for key in aggregate_fields:
            technical.pop(key, None)
        parent[path[-1]] = technical
    return projection


def _count_source_contract_rows(
    database_path: Path,
    *,
    symbols: tuple[str, ...],
) -> int:
    """在來源重播前界定合約內容重驗會讀取的歷史列數。"""

    placeholders = ",".join("?" for _ in symbols)
    if not placeholders:
        raise PersonalCandidateInventoryError(
            "training_source_time_proof_training_rows_invalid"
        )
    total = 0
    with sqlite3.connect(database_path.as_uri() + "?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        for table, symbol_column in (
            ("technical_indicators", "證券代號"),
            ("corporate_action_adjustments", "symbol"),
        ):
            count = connection.execute(
                f'SELECT COUNT(*) FROM "{table}" '
                f'WHERE "{symbol_column}" IN ({placeholders})',
                symbols,
            ).fetchone()
            if count is None or type(count[0]) is not int or count[0] < 0:
                raise PersonalCandidateInventoryError(
                    "training_source_time_proof_source_row_count_invalid"
                )
            total += count[0]
            if total > MAX_SOURCE_PROOF_CONTRACT_ROWS:
                break
    return total


def _source_proof_failure_code(exc: Exception) -> str:
    text = str(exc)
    if text.startswith("training_source_time_"):
        return text.split(":", 1)[0]
    if "file_size_limit_exceeded" in text:
        return "training_source_time_proof_budget_exceeded"
    if "path" in text and ("逸出" in text or "symlink" in text or "junction" in text):
        return "training_source_time_proof_path_rejected"
    if isinstance(exc, FileNotFoundError):
        return "training_source_time_proof_source_missing"
    return "training_source_time_proof_invalid"


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _unavailable_entry(
    candidate_root: str | Path,
    payload: Mapping[str, Any],
    *,
    reason_code: str,
    next_step: str,
    status: str = "unavailable",
) -> PersonalCandidateInventoryEntryV1:
    root = Path(candidate_root)
    candidate_id = payload.get("candidate_id")
    if type(candidate_id) is not str:
        candidate_id = root.name if root.name else None
    return PersonalCandidateInventoryEntryV1(
        candidate_id=candidate_id,
        candidate_root=str(root),
        status=status,
        reason_code=reason_code,
        display_label=str(candidate_id or "無法識別的候選"),
        candidate_frozen_at=_optional_text(payload.get("candidate_frozen_at")),
        training_as_of=_optional_text(payload.get("training_as_of")),
        training_semantics=_optional_text(payload.get("training_semantics")),
        decision_time_eligible=(
            payload.get("decision_time_eligible")
            if type(payload.get("decision_time_eligible")) is bool
            else None
        ),
        dataset_id=_optional_text(payload.get("dataset_id")),
        training_row_count=_optional_int(payload.get("training_row_count")),
        calibration_sample_count=_optional_int(payload.get("calibration_sample_count")),
        calibration_gap_bp=_optional_int(payload.get("calibration_gap_bp")),
        candidate_blockers=(),
        next_step=next_step,
        candidate=None,
    )


def _validated_candidate_root(candidate_root: Path, learning_root: Path) -> Path:
    if not candidate_root.is_absolute():
        raise PersonalCandidateInventoryError("candidate_root 必須是絕對路徑")
    _reject_reparse_components(candidate_root)
    root = candidate_root.resolve(strict=True)
    if not _is_within(root, learning_root):
        raise PersonalCandidateInventoryError("candidate_root 必須位於已設定 learning root 內")
    relative = root.relative_to(learning_root)
    parts = relative.parts
    if not (
        len(parts) == 4
        and parts[0] == "runs"
        and _is_iso_day(parts[1])
        and parts[2] == "candidates"
    ) and not (
        len(parts) == 5
        and parts[0] == "runs"
        and _is_iso_day(parts[1])
        and parts[3] == "candidates"
    ):
        raise PersonalCandidateInventoryError("candidate_root 不符合固定 runs/day[/scope]/candidates/id 形狀")
    if not _is_safe_directory(root):
        raise PersonalCandidateInventoryError("candidate_root 不是一般目錄")
    return root


def _ensure_directory_inside(path: Path, root: Path) -> None:
    _reject_reparse_components(path)
    resolved = path.resolve(strict=True)
    if not _is_within(resolved, root) or not _is_safe_directory(resolved):
        raise PersonalCandidateInventoryError("清冊目錄不在設定 learning root 內")


def _reject_reparse_components(path: Path) -> None:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        try:
            if current.is_symlink() or _is_junction(current):
                raise PersonalCandidateInventoryError("清冊路徑不可經過 symlink/junction")
        except OSError as exc:
            raise PersonalCandidateInventoryError("無法檢查清冊路徑元件") from exc


def _is_junction(path: Path) -> bool:
    junction_check = getattr(path, "is_junction", None)
    return bool(junction_check()) if callable(junction_check) else False


def _is_safe_directory(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(info, "st_file_attributes", 0)
    return (
        stat.S_ISDIR(info.st_mode)
        and not path.is_symlink()
        and not (reparse and attributes & reparse)
    )


def _directory_state(path: Path) -> str:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "unreadable"
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(info, "st_file_attributes", 0)
    if (
        not stat.S_ISDIR(info.st_mode)
        or path.is_symlink()
        or (reparse and attributes & reparse)
    ):
        return "unsafe"
    return "directory"


def _read_bounded_file(path: Path, *, root: Path, maximum_bytes: int) -> bytes:
    _reject_reparse_components(path)
    if not _is_within(path.resolve(strict=True), root):
        raise PersonalCandidateInventoryError("候選檔案逸出 learning root")
    before = _regular_file_stat(path)
    if before.st_size > maximum_bytes:
        raise PersonalCandidateInventoryError(f"file_size_limit_exceeded:{maximum_bytes}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            opened = os.fstat(handle.fileno())
            _same_file_version(before, opened)
            raw = handle.read(maximum_bytes + 1)
            after_open = os.fstat(handle.fileno())
        if len(raw) > maximum_bytes:
            raise PersonalCandidateInventoryError(f"file_size_limit_exceeded:{maximum_bytes}")
        after_path = _regular_file_stat(path)
        _same_file_version(opened, after_open)
        _same_file_version(opened, after_path)
        if len(raw) != after_open.st_size:
            raise PersonalCandidateInventoryError("file_changed_during_read")
        return raw
    finally:
        os.close(descriptor)


def _hash_bounded_file(
    path: Path,
    *,
    root: Path,
    maximum_bytes: int,
    progress_callback: ProgressCallback | None,
    cancellation_requested: CancellationCheck | None,
) -> str:
    _reject_reparse_components(path)
    if not _is_within(path.resolve(strict=True), root):
        raise PersonalCandidateInventoryError("artifact 逸出 learning root")
    before = _regular_file_stat(path)
    if before.st_size > maximum_bytes:
        raise PersonalCandidateInventoryError(f"artifact_size_limit_exceeded:{maximum_bytes}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    digest = hashlib.sha256()
    read_bytes = 0
    try:
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            opened = os.fstat(handle.fileno())
            _same_file_version(before, opened)
            while True:
                _check_cancelled(cancellation_requested)
                block = handle.read(_HASH_CHUNK_BYTES)
                if not block:
                    break
                read_bytes += len(block)
                if read_bytes > maximum_bytes:
                    raise PersonalCandidateInventoryError(
                        f"artifact_size_limit_exceeded:{maximum_bytes}"
                    )
                digest.update(block)
                _emit_progress(
                    progress_callback,
                    stage="hash_artifact",
                    completed=read_bytes,
                    total=opened.st_size,
                    path=path,
                )
            after_open = os.fstat(handle.fileno())
        after_path = _regular_file_stat(path)
        _same_file_version(opened, after_open)
        _same_file_version(opened, after_path)
        if read_bytes != after_open.st_size:
            raise PersonalCandidateInventoryError("artifact_changed_during_hash")
        return f"sha256:{digest.hexdigest()}"
    finally:
        os.close(descriptor)


def _regular_file_stat(path: Path) -> os.stat_result:
    info = path.lstat()
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(info, "st_file_attributes", 0)
    if (
        not stat.S_ISREG(info.st_mode)
        or path.is_symlink()
        or (reparse and attributes & reparse)
    ):
        raise PersonalCandidateInventoryError("候選檔案必須是一般檔案")
    return info


def _same_file_version(first: os.stat_result, second: os.stat_result) -> None:
    identity_first = (first.st_dev, first.st_ino, first.st_size, first.st_mtime_ns)
    identity_second = (second.st_dev, second.st_ino, second.st_size, second.st_mtime_ns)
    if identity_first != identity_second:
        raise PersonalCandidateInventoryError("候選檔案在讀取期間變更")


def _json_mapping(raw: bytes, field_name: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
            parse_float=_finite_json_float,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise PersonalCandidateInventoryError(f"{field_name} JSON 無效") from exc
    if type(value) is not dict:
        raise PersonalCandidateInventoryError(f"{field_name} 必須是 JSON object")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"非標準 JSON 數值不允許:{value}")


def _finite_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("JSON 浮點欄位不可為 non-finite")
    return parsed


def _parse_manifest(payload: Mapping[str, Any]) -> Any:
    from ml_module.model_artifact_manifest import ModelArtifactManifest

    return ModelArtifactManifest.from_dict(payload)


def _validate_candidate_manifest_binding(
    candidate: Mapping[str, Any],
    manifest: Any,
) -> None:
    if candidate.get("shadow_only") is not True:
        raise PersonalCandidateInventoryError("candidate shadow_only flag 無效")
    if candidate.get("production_eligible") is not False:
        raise PersonalCandidateInventoryError("candidate production_eligible flag 無效")
    if candidate.get("production_action_allowed") is not False:
        raise PersonalCandidateInventoryError("candidate production_action_allowed flag 無效")
    bindings = {
        "candidate_id": manifest.model_id,
        "model_id": manifest.model_id,
        "dataset_id": manifest.dataset_id,
        "dataset_hash": candidate.get("dataset_hash"),
        "manifest_hash": manifest.manifest_hash,
        "artifact_hash": manifest.artifact_hash,
        "training_as_of": manifest.training_as_of,
    }
    if candidate.get("candidate_id") != bindings["candidate_id"]:
        raise PersonalCandidateInventoryError("candidate/model identity 不一致")
    for key in ("model_id", "dataset_id", "dataset_hash", "manifest_hash", "artifact_hash", "training_as_of"):
        if candidate.get(key) != bindings[key]:
            raise PersonalCandidateInventoryError(f"candidate/manifest 欄位不一致:{key}")
    if candidate.get("candidate_freeze_hash") is None:
        raise PersonalCandidateInventoryError("candidate_freeze_hash 缺少")
    if candidate.get("candidate_frozen_at") != manifest.created_at:
        raise PersonalCandidateInventoryError("candidate freeze 時間與 manifest 不一致")
    schema = candidate.get("feature_schema")
    if not isinstance(schema, list) or tuple(tuple(item) for item in schema) != manifest.feature_schema:
        raise PersonalCandidateInventoryError("candidate feature schema 與 manifest 不一致")


def _candidate_freeze_hash(candidate: Mapping[str, Any], manifest: Any) -> str:
    from ml_module.recommendation_calibration_training import candidate_freeze_hash

    evaluation = candidate.get("evaluation")
    if not isinstance(evaluation, Mapping):
        raise PersonalCandidateInventoryError("candidate evaluation 欄位無效")
    actual = candidate_freeze_hash(
        candidate_id=str(candidate.get("candidate_id") or ""),
        dataset_hash=str(candidate.get("dataset_hash") or ""),
        manifest_hash=manifest.manifest_hash,
        artifact_hash=manifest.artifact_hash,
        evaluation=evaluation,
    )
    if actual != candidate.get("candidate_freeze_hash"):
        raise PersonalCandidateInventoryError("candidate freeze hash mismatch")
    return actual


def _validate_lineage_snapshot(
    *,
    root: Path,
    learning_root: Path,
    candidate_payload: Mapping[str, Any],
    cancellation_requested: CancellationCheck | None,
    progress_callback: ProgressCallback | None,
) -> tuple[str, dict[str, Any] | None]:
    hash_declared = "training_lineage_manifest_hash" in candidate_payload
    path_declared = "training_lineage_manifest_path" in candidate_payload
    if not hash_declared and not path_declared:
        return "legacy_unproven", None
    lineage_hash = candidate_payload.get("training_lineage_manifest_hash")
    lineage_path_text = candidate_payload.get("training_lineage_manifest_path")
    if (
        not _is_sha256(lineage_hash)
        or type(lineage_path_text) is not str
        or not lineage_path_text.strip()
    ):
        raise PersonalCandidateInventoryError("training lineage declaration 無效")
    lineage_path = Path(lineage_path_text)
    if not lineage_path.is_absolute():
        lineage_path = root / lineage_path
    _reject_reparse_components(lineage_path)
    resolved_path = lineage_path.resolve(strict=True)
    if not _is_within(resolved_path, learning_root):
        raise PersonalCandidateInventoryError("training lineage path 逸出 learning root")
    lineage_bytes = _read_bounded_file(
        resolved_path,
        root=learning_root,
        maximum_bytes=MAX_LINEAGE_JSON_BYTES,
    )
    _json_mapping(lineage_bytes, "lineage.json")
    _emit_progress(
        progress_callback,
        stage="validate_training_lineage",
        completed=len(lineage_bytes),
        total=len(lineage_bytes),
        path=resolved_path,
    )
    _check_cancelled(cancellation_requested)

    # 公開 lineage reader 接受路徑；將已受限讀取的同一組 bytes 放進一次性暫存，
    # 避免 reader 二次讀取可變原檔，也重用其完整 hash/PIT/identity 驗證。
    with tempfile.TemporaryDirectory(prefix="personal_candidate_lineage_") as temporary_root:
        snapshot_path = Path(temporary_root) / "lineage.json"
        snapshot_path.write_bytes(lineage_bytes)
        from ml_module.recommendation_training_lineage import (
            read_recommendation_training_lineage,
        )

        lineage = read_recommendation_training_lineage(
            snapshot_path,
            expected_manifest_hash=str(lineage_hash),
            expected_dataset_hash=str(candidate_payload.get("dataset_hash") or ""),
            expected_candidate_id=str(candidate_payload.get("candidate_id") or ""),
        )
        payload = lineage.to_dict()
    expected_path = (
        learning_root
        / "training_lineage"
        / str(payload.get("decision_date") or "")
        / str(lineage_hash).split(":", 1)[1]
        / "lineage.json"
    ).resolve(strict=True)
    if resolved_path != expected_path:
        raise PersonalCandidateInventoryError("training lineage path 與 deterministic identity 不一致")
    if payload.get("candidate_manifest_hash") != candidate_payload.get("manifest_hash"):
        raise PersonalCandidateInventoryError("training lineage manifest binding 不一致")
    if payload.get("candidate_artifact_hash") != candidate_payload.get("artifact_hash"):
        raise PersonalCandidateInventoryError("training lineage artifact binding 不一致")
    return "verified", payload


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _is_iso_day(value: str) -> bool:
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _is_sha256(value: Any) -> bool:
    return type(value) is str and _SHA256_RE.fullmatch(value) is not None


def _sha256_bytes(raw: bytes) -> str:
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _optional_text(value: Any) -> str | None:
    return value if type(value) is str and value else None


def _optional_int(value: Any) -> int | None:
    return value if type(value) is int else None


def _reason_code(exc: BaseException) -> str:
    text = str(exc)
    if "freeze 時間" in text:
        return "candidate_frozen_at_mismatch"
    if text.startswith("file_size_limit_exceeded:"):
        return "candidate_json_size_limit_exceeded"
    if text.startswith("artifact_size_limit_exceeded:"):
        return "artifact_size_limit_exceeded"
    if (
        "逸出" in text
        or "learning root" in text
        or "symlink" in text
        or "junction" in text
    ):
        return "path_outside_or_reparse_rejected"
    if isinstance(exc, FileNotFoundError):
        return "required_file_missing"
    if "lineage" in text:
        return "training_lineage_invalid"
    if "manifest" in text:
        return "manifest_invalid"
    if "artifact" in text:
        return "artifact_invalid"
    return "candidate_contract_invalid"


def _check_cancelled(check: CancellationCheck | None) -> None:
    if check is not None and check():
        raise PersonalCandidateInventoryCancelled("個人候選檢查已由呼叫端取消")


def _emit_progress(
    callback: ProgressCallback | None,
    *,
    stage: str,
    completed: int,
    total: int | None,
    path: Path,
) -> None:
    if callback is not None:
        callback(
            PersonalCandidateInventoryProgressV1(
                stage=stage,
                completed=completed,
                total=total,
                current_path=str(path),
            )
        )
