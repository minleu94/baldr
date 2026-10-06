"""推薦校準的明示個人使用設定與本機版本保存。"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Iterator, Mapping, Protocol, cast


PERSONAL_USE_POLICY_SCHEMA_V1 = "recommendation-personal-use-policy.v1"
PERSONAL_USE_POLICY_VERSION = 1
PERSONAL_USE_POLICY_SCHEMA_V2 = "recommendation-personal-use-policy.v2"
PERSONAL_USE_POLICY_VERSION_V2 = 2
PERSONAL_SOURCE_TIME_BINDING_PROPOSAL_SCHEMA_V1 = (
    "personal-source-time-binding-proposal.v1"
)
PERSONAL_SOURCE_TIME_TRUST_SCHEMA_V1 = "personal-user-declared-source-time-trust.v1"
RULE_ONLY_MODE = "rule_only"
PERSONAL_CALIBRATED_PROBABILITY_MODE = "personal_calibrated_probability"
PERSONAL_USE_MODES = frozenset({RULE_ONLY_MODE, PERSONAL_CALIBRATED_PROBABILITY_MODE})
DEFAULT_RULE_ONLY_BASELINE_ID = "recommendation_rule_only_default_v1"
PERSONAL_PROBABILITY_CHANGE_CAP_BP = 1_000


class PersonalUsePolicyError(ValueError):
    """個人使用設定格式或保存狀態無效。"""


class PersonalUsePolicyConflict(PersonalUsePolicyError):
    """設定版本已變更；呼叫端必須重新讀取後再確認。"""


class _PosixFileLockAPI(Protocol):
    LOCK_EX: int
    LOCK_NB: int
    LOCK_UN: int

    def flock(self, file_descriptor: int, operation: int) -> None: ...


@dataclass(frozen=True)
class PersonalCalibrationCandidateV1:
    """由唯讀候選 inventory 提供、供 consumer 再驗證的 artifact identity。"""

    candidate_id: str
    candidate_root: str
    candidate_json_sha256: str
    candidate_manifest_hash: str
    candidate_artifact_hash: str
    candidate_freeze_hash: str
    dataset_hash: str

    def __post_init__(self) -> None:
        if type(self.candidate_id) is not str or not self.candidate_id.strip():
            raise PersonalUsePolicyError("candidate_id 不可為空")
        if type(self.candidate_root) is not str or not self.candidate_root.strip():
            raise PersonalUsePolicyError("candidate_root 不可為空")
        if not Path(self.candidate_root).is_absolute():
            raise PersonalUsePolicyError("candidate_root 必須是絕對路徑")
        for name in (
            "candidate_json_sha256",
            "candidate_manifest_hash",
            "candidate_artifact_hash",
            "candidate_freeze_hash",
            "dataset_hash",
        ):
            if not _is_sha256(getattr(self, name)):
                raise PersonalUsePolicyError(f"{name} 必須是 sha256:<64位小寫hex>")

    def to_dict(self) -> dict[str, str]:
        return {
            "candidate_id": self.candidate_id,
            "candidate_root": self.candidate_root,
            "candidate_json_sha256": self.candidate_json_sha256,
            "candidate_manifest_hash": self.candidate_manifest_hash,
            "candidate_artifact_hash": self.candidate_artifact_hash,
            "candidate_freeze_hash": self.candidate_freeze_hash,
            "dataset_hash": self.dataset_hash,
        }


@dataclass(frozen=True)
class RecommendationPersonalUseSelectionV1:
    """一次明示的個人策略選擇；不包含可回填的確認時間或版本。"""

    scope_id: str
    mode: str
    candidate: PersonalCalibrationCandidateV1 | None = None

    def __post_init__(self) -> None:
        if type(self.scope_id) is not str or not _valid_scope_id(self.scope_id):
            raise PersonalUsePolicyError("scope_id 必須是非空 ASCII 識別字")
        if self.mode not in PERSONAL_USE_MODES:
            raise PersonalUsePolicyError("不支援的個人使用模式")
        if self.mode == "personal_calibrated_probability" and type(
            self.candidate
        ) is not PersonalCalibrationCandidateV1:
            raise PersonalUsePolicyError("個人校準模式必須明示候選 artifact identity")
        if self.candidate is not None and type(self.candidate) is not PersonalCalibrationCandidateV1:
            raise PersonalUsePolicyError("candidate 必須是 PersonalCalibrationCandidateV1")


@dataclass(frozen=True)
class PersonalSourceFileIdentityV1:
    """明示來源 SQLite 檔案的作業系統識別欄位。"""

    device: int
    inode: int

    def __post_init__(self) -> None:
        if type(self.device) is not int or self.device < 0:
            raise PersonalUsePolicyError("source file device 必須是非負整數")
        if type(self.inode) is not int or self.inode < 0:
            raise PersonalUsePolicyError("source file inode 必須是非負整數")

    def to_dict(self) -> dict[str, int]:
        return {"device": self.device, "inode": self.inode}


@dataclass(frozen=True)
class PersonalSourceReplayScopeV1:
    """由指定來源資料庫實際重播取得的日期、資料集與標的範圍。"""

    dataset_ids: tuple[str, ...]
    decision_dates: tuple[str, ...]
    symbols: tuple[str, ...]
    sample_count: int

    def __post_init__(self) -> None:
        for name, values in (
            ("dataset_ids", self.dataset_ids),
            ("decision_dates", self.decision_dates),
            ("symbols", self.symbols),
        ):
            if type(values) is not tuple or any(
                type(value) is not str or not value.strip() for value in values
            ):
                raise PersonalUsePolicyError(f"replay_scope.{name} 必須是非空字串 tuple")
            if len(values) != len(set(values)):
                raise PersonalUsePolicyError(f"replay_scope.{name} 不可重複")
        for value in self.decision_dates:
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError as exc:
                raise PersonalUsePolicyError("replay_scope 日期格式無效") from exc
            if parsed.tzinfo is not None or len(value) != 10:
                raise PersonalUsePolicyError("replay_scope 日期必須是 YYYY-MM-DD")
        if type(self.sample_count) is not int or self.sample_count < 1:
            raise PersonalUsePolicyError("replay_scope.sample_count 必須是正整數")

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_ids": list(self.dataset_ids),
            "decision_dates": list(self.decision_dates),
            "symbols": list(self.symbols),
            "sample_count": self.sample_count,
        }


@dataclass(frozen=True)
class PersonalSourceTimeBindingProposalV1:
    """來源檢查提案；它本身不代表使用者已同意，也不會解鎖模型。"""

    source_database_path: str
    file_identity: PersonalSourceFileIdentityV1
    source_database_size_bytes: int
    source_slice_sha256: str
    candidate: PersonalCalibrationCandidateV1
    replay_scope: PersonalSourceReplayScopeV1
    schema_version: str = PERSONAL_SOURCE_TIME_BINDING_PROPOSAL_SCHEMA_V1
    basis: str = "user_declared_source_time"
    research_only: bool = True
    official_historical_pit_verified: bool = False

    def __post_init__(self) -> None:
        _validate_source_binding_fields(
            schema_version=self.schema_version,
            expected_schema=PERSONAL_SOURCE_TIME_BINDING_PROPOSAL_SCHEMA_V1,
            basis=self.basis,
            source_database_path=self.source_database_path,
            file_identity=self.file_identity,
            source_database_size_bytes=self.source_database_size_bytes,
            source_slice_sha256=self.source_slice_sha256,
            candidate=self.candidate,
            replay_scope=self.replay_scope,
            research_only=self.research_only,
            official_historical_pit_verified=self.official_historical_pit_verified,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "basis": self.basis,
            "source_database_path": self.source_database_path,
            "file_identity": self.file_identity.to_dict(),
            "source_database_size_bytes": self.source_database_size_bytes,
            "source_slice_sha256": self.source_slice_sha256,
            "candidate": self.candidate.to_dict(),
            "replay_scope": self.replay_scope.to_dict(),
            "research_only": self.research_only,
            "official_historical_pit_verified": self.official_historical_pit_verified,
        }


@dataclass(frozen=True)
class PersonalSourceTimeTrustV1:
    """已確認的 user-declared source-time binding，供執行時重新驗證。"""

    source_database_path: str
    file_identity: PersonalSourceFileIdentityV1
    source_database_size_bytes: int
    source_slice_sha256: str
    candidate: PersonalCalibrationCandidateV1
    replay_scope: PersonalSourceReplayScopeV1
    confirmed_at: str
    schema_version: str = PERSONAL_SOURCE_TIME_TRUST_SCHEMA_V1
    basis: str = "user_declared_source_time"
    research_only: bool = True
    official_historical_pit_verified: bool = False

    def __post_init__(self) -> None:
        _validate_source_binding_fields(
            schema_version=self.schema_version,
            expected_schema=PERSONAL_SOURCE_TIME_TRUST_SCHEMA_V1,
            basis=self.basis,
            source_database_path=self.source_database_path,
            file_identity=self.file_identity,
            source_database_size_bytes=self.source_database_size_bytes,
            source_slice_sha256=self.source_slice_sha256,
            candidate=self.candidate,
            replay_scope=self.replay_scope,
            research_only=self.research_only,
            official_historical_pit_verified=self.official_historical_pit_verified,
        )
        if not _aware_utc_timestamp(self.confirmed_at):
            raise PersonalUsePolicyError("source-time confirmed_at 必須是 canonical UTC")

    @classmethod
    def from_proposal(
        cls, proposal: PersonalSourceTimeBindingProposalV1, *, confirmed_at: str
    ) -> "PersonalSourceTimeTrustV1":
        if type(proposal) is not PersonalSourceTimeBindingProposalV1:
            raise PersonalUsePolicyError("source_time_binding 必須是已檢查的 proposal DTO")
        return cls(
            source_database_path=proposal.source_database_path,
            file_identity=proposal.file_identity,
            source_database_size_bytes=proposal.source_database_size_bytes,
            source_slice_sha256=proposal.source_slice_sha256,
            candidate=proposal.candidate,
            replay_scope=proposal.replay_scope,
            confirmed_at=confirmed_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "basis": self.basis,
            "confirmed_at": self.confirmed_at,
            "source_database_path": self.source_database_path,
            "file_identity": self.file_identity.to_dict(),
            "source_database_size_bytes": self.source_database_size_bytes,
            "source_slice_sha256": self.source_slice_sha256,
            "candidate": self.candidate.to_dict(),
            "replay_scope": self.replay_scope.to_dict(),
            "research_only": self.research_only,
            "official_historical_pit_verified": self.official_historical_pit_verified,
        }


@dataclass(frozen=True)
class RecommendationPersonalUseSelectionV2:
    """V2 明示選擇；來源信任只可由檢查提案建立。"""

    scope_id: str
    mode: str
    source_time_binding: PersonalSourceTimeBindingProposalV1 | None = None

    def __post_init__(self) -> None:
        if type(self.scope_id) is not str or not _valid_scope_id(self.scope_id):
            raise PersonalUsePolicyError("scope_id 必須是非空 ASCII 識別字")
        if type(self.mode) is not str or self.mode not in PERSONAL_USE_MODES:
            raise PersonalUsePolicyError("不支援的個人使用模式")
        if self.mode == PERSONAL_CALIBRATED_PROBABILITY_MODE and type(
            self.source_time_binding
        ) is not PersonalSourceTimeBindingProposalV1:
            raise PersonalUsePolicyError("校準模式必須明示來源時間檢查提案")
        if self.mode == RULE_ONLY_MODE and self.source_time_binding is not None:
            raise PersonalUsePolicyError("rule_only 必須明確清除來源時間信任")
        if self.source_time_binding is not None and type(
            self.source_time_binding
        ) is not PersonalSourceTimeBindingProposalV1:
            raise PersonalUsePolicyError("source_time_binding 型別錯誤")


@dataclass(frozen=True)
class RecommendationPersonalUsePolicyV1:
    """已持久化、版本化且綁定本機個人設定檔的策略快照。"""

    revision: int
    scope_id: str
    mode: str
    confirmed_at: str | None
    candidate: PersonalCalibrationCandidateV1 | None
    policy_sha256: str
    storage_path: Path | None = field(compare=False, repr=False)
    storage_bytes: bytes | None = field(compare=False, repr=False, default=None)
    rollback_of_revision: int | None = None
    rollback_of_policy_sha256: str | None = None

    @property
    def version(self) -> int:
        return PERSONAL_USE_POLICY_VERSION

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "schema_version": PERSONAL_USE_POLICY_SCHEMA_V1,
            "policy_version": PERSONAL_USE_POLICY_VERSION,
            "revision": self.revision,
            "scope_id": self.scope_id,
            "mode": self.mode,
            "confirmed_at": self.confirmed_at,
            "candidate": self.candidate.to_dict() if self.candidate is not None else None,
        }
        if self.storage_path is None:
            body["baseline_identity"] = DEFAULT_RULE_ONLY_BASELINE_ID
        if self.rollback_of_revision is not None:
            body["rollback_of_revision"] = self.rollback_of_revision
            body["rollback_of_policy_sha256"] = self.rollback_of_policy_sha256
        body["policy_sha256"] = self.policy_sha256
        return body

    def validate_snapshot(self) -> "RecommendationPersonalUsePolicyV1":
        """驗證此 DTO 的完整 schema、hash 與其不可變保存 bytes。"""

        if self.storage_path is None:
            expected = type(self).default_rule_only(self.scope_id)
            if self.storage_bytes is not None or self.to_dict() != expected.to_dict():
                raise PersonalUsePolicyError("未保存設定只允許固定 rule-only baseline")
            return expected
        if type(self.storage_bytes) is not bytes:
            raise PersonalUsePolicyError("已保存設定缺少原始 snapshot bytes")
        path = _explicit_policy_path(self.storage_path)
        decoded = _decode_policy(self.storage_bytes, path)
        if decoded.to_dict() != self.to_dict():
            raise PersonalUsePolicyError("policy DTO 與已驗證 snapshot bytes 不一致")
        return decoded

    @classmethod
    def default_rule_only(cls, scope_id: str) -> "RecommendationPersonalUsePolicyV1":
        """建立未確認、不落盤的明確 rule-only 冷啟動設定。"""

        selection = RecommendationPersonalUseSelectionV1(
            scope_id=scope_id,
            mode=RULE_ONLY_MODE,
        )
        body = {
            "schema_version": PERSONAL_USE_POLICY_SCHEMA_V1,
            "policy_version": PERSONAL_USE_POLICY_VERSION,
            "revision": 0,
            "scope_id": selection.scope_id,
            "mode": RULE_ONLY_MODE,
            "confirmed_at": None,
            "candidate": None,
            "baseline_identity": DEFAULT_RULE_ONLY_BASELINE_ID,
        }
        return cls(
            revision=0,
            scope_id=selection.scope_id,
            mode=RULE_ONLY_MODE,
            confirmed_at=None,
            candidate=None,
            policy_sha256=_policy_hash(body),
            storage_path=None,
            storage_bytes=None,
        )

    def applicable_at(self, decision_at: str | datetime) -> bool:
        """確認時間須不晚於實際 producer clock；拒絕 naive 或無效時間。"""

        if self.revision == 0:
            return self.mode == RULE_ONLY_MODE and self.confirmed_at is None
        if self.confirmed_at is None:
            return False

        try:
            confirmed = datetime.fromisoformat(self.confirmed_at.replace("Z", "+00:00"))
            if type(decision_at) is str:
                decision = datetime.fromisoformat(decision_at.replace("Z", "+00:00"))
            elif isinstance(decision_at, datetime):
                decision = decision_at
            else:
                return False
        except (TypeError, ValueError):
            return False
        if (
            confirmed.tzinfo is None
            or confirmed.utcoffset() is None
            or decision.tzinfo is None
            or decision.utcoffset() is None
        ):
            return False
        return confirmed.astimezone(timezone.utc) <= decision.astimezone(timezone.utc)


@dataclass(frozen=True)
class RecommendationPersonalUsePolicyV2:
    """V2 個人設定；模型模式另綁定使用者明示的來源時間檢查。"""

    revision: int
    scope_id: str
    mode: str
    confirmed_at: str
    candidate: PersonalCalibrationCandidateV1 | None
    source_time_trust: PersonalSourceTimeTrustV1 | None
    policy_sha256: str
    storage_path: Path | None = field(compare=False, repr=False)
    storage_bytes: bytes | None = field(compare=False, repr=False, default=None)
    rollback_of_revision: int | None = None
    rollback_of_policy_sha256: str | None = None

    @property
    def version(self) -> int:
        return PERSONAL_USE_POLICY_VERSION_V2

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "schema_version": PERSONAL_USE_POLICY_SCHEMA_V2,
            "policy_version": PERSONAL_USE_POLICY_VERSION_V2,
            "revision": self.revision,
            "scope_id": self.scope_id,
            "mode": self.mode,
            "confirmed_at": self.confirmed_at,
            "candidate": self.candidate.to_dict() if self.candidate is not None else None,
            "source_time_trust": (
                self.source_time_trust.to_dict()
                if self.source_time_trust is not None
                else None
            ),
        }
        if self.rollback_of_revision is not None:
            body["rollback_of_revision"] = self.rollback_of_revision
            body["rollback_of_policy_sha256"] = self.rollback_of_policy_sha256
        body["policy_sha256"] = self.policy_sha256
        return body

    def validate_snapshot(self) -> "RecommendationPersonalUsePolicyV2":
        """以原保存 bytes 重驗完整 V2 schema/hash 和來源信任欄位。"""

        if self.storage_path is None or type(self.storage_bytes) is not bytes:
            raise PersonalUsePolicyError("V2 policy 必須是已保存且綁定原始 bytes 的快照")
        path = _explicit_policy_path(self.storage_path)
        decoded = _decode_policy_v2(self.storage_bytes, path)
        if decoded.to_dict() != self.to_dict():
            raise PersonalUsePolicyError("V2 policy DTO 與已驗證 snapshot bytes 不一致")
        return decoded

    def applicable_at(self, decision_at: str | datetime) -> bool:
        """政策確認時間不得晚於實際 aware 決策時鐘。"""

        if not self.confirmed_at:
            return False
        try:
            confirmed = datetime.fromisoformat(self.confirmed_at.replace("Z", "+00:00"))
            if type(decision_at) is str:
                decision = datetime.fromisoformat(decision_at.replace("Z", "+00:00"))
            elif isinstance(decision_at, datetime):
                decision = decision_at
            else:
                return False
        except (TypeError, ValueError):
            return False
        if (
            confirmed.tzinfo is None
            or confirmed.utcoffset() is None
            or decision.tzinfo is None
            or decision.utcoffset() is None
        ):
            return False
        return confirmed.astimezone(timezone.utc) <= decision.astimezone(timezone.utc)


def load_personal_use_policy(
    path: str | Path,
) -> RecommendationPersonalUsePolicyV1:
    """讀取並驗證呼叫端指定的本機個人設定檔。"""

    policy_path = _explicit_policy_path(path)
    try:
        raw = policy_path.read_bytes()
    except OSError as exc:
        raise PersonalUsePolicyError(f"無法讀取個人設定檔：{exc}") from exc
    return _decode_policy(raw, policy_path)


def load_personal_use_policy_v2(
    path: str | Path,
) -> RecommendationPersonalUsePolicyV2:
    """讀取並驗證呼叫端指定的 V2 個人設定檔。"""

    policy_path = _explicit_policy_path(path)
    try:
        raw = policy_path.read_bytes()
    except OSError as exc:
        raise PersonalUsePolicyError(f"無法讀取個人設定檔：{exc}") from exc
    return _decode_policy_v2(raw, policy_path)


def load_personal_use_policy_snapshot(
    path: str | Path,
) -> RecommendationPersonalUsePolicyV1 | RecommendationPersonalUsePolicyV2:
    """讀取已保存的 V1 或 V2 設定；回傳物件綁定實際讀取 bytes。"""

    policy_path = _explicit_policy_path(path)
    try:
        raw = policy_path.read_bytes()
    except OSError as exc:
        raise PersonalUsePolicyError(f"無法讀取個人設定檔：{exc}") from exc
    return _decode_policy_snapshot(raw, policy_path)


def validate_personal_use_policy_snapshot(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """驗證 V1/V2 已保存或冷啟動快照，不讀取任何設定檔。"""

    payload = _snapshot_json_mapping(value)
    revision = payload.get("revision")
    if type(revision) is int and revision == 0:
        scope_id = payload.get("scope_id")
        if type(scope_id) is not str:
            raise PersonalUsePolicyError("冷啟動政策 scope_id 無效")
        baseline = RecommendationPersonalUsePolicyV1.default_rule_only(scope_id)
        if payload != baseline.to_dict():
            raise PersonalUsePolicyError("revision 0 僅允許固定 rule-only baseline")
        return baseline.to_dict()

    try:
        raw = (
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PersonalUsePolicyError("政策快照不是有效 JSON object") from exc
    decoded = _decode_policy_snapshot(raw, Path("personal-use-policy-snapshot.json"))
    canonical = decoded.to_dict()
    if canonical != payload:
        raise PersonalUsePolicyError("政策快照不是 canonical schema")
    return canonical


def _snapshot_json_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PersonalUsePolicyError("政策快照必須是 object")

    def copy_json(item: Any, field_name: str) -> Any:
        if isinstance(item, Mapping):
            copied: dict[str, Any] = {}
            for key, nested in item.items():
                if type(key) is not str or not key:
                    raise PersonalUsePolicyError(
                        f"{field_name} 的 key 必須是非空字串"
                    )
                copied[key] = copy_json(nested, f"{field_name}.{key}")
            return copied
        if isinstance(item, (list, tuple)):
            return [copy_json(nested, f"{field_name}[]") for nested in item]
        if item is None or type(item) in (str, int, bool):
            return item
        raise PersonalUsePolicyError(
            f"{field_name} 含不支援的 JSON 值 {type(item).__name__}"
        )

    copied = copy_json(value, "policy_snapshot")
    if type(copied) is not dict:
        raise PersonalUsePolicyError("政策快照根節點必須是 object")
    return copied


def save_personal_use_policy(
    path: str | Path,
    selection: RecommendationPersonalUseSelectionV1,
    *,
    expected_revision: int,
) -> RecommendationPersonalUsePolicyV1:
    """以跨程序鎖與 revision compare-and-swap 保存已確認選擇。"""

    if type(selection) is not RecommendationPersonalUseSelectionV1:
        raise TypeError("selection 必須是 RecommendationPersonalUseSelectionV1")
    if type(expected_revision) is not int or expected_revision < 0:
        raise PersonalUsePolicyError("expected_revision 必須是非負整數")
    policy_path = _explicit_policy_path(path)
    with _interprocess_lock(policy_path):
        current_raw = _read_optional_bytes(policy_path)
        current_revision = _revision_from_bytes(current_raw, policy_path)
        if current_revision != expected_revision:
            raise PersonalUsePolicyConflict(
                f"個人設定版本衝突：expected={expected_revision}, current={current_revision}"
            )
        if current_raw is not None:
            _archive_revision(policy_path, current_raw)
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        )
        return _write_new_revision(
            policy_path,
            selection,
            revision=current_revision + 1,
            confirmed_at=now,
        )


def rollback_personal_use_policy(
    path: str | Path,
    *,
    target_revision: int,
    target_policy_sha256: str,
    expected_revision: int,
) -> RecommendationPersonalUsePolicyV1:
    """將已驗證的歷史選擇另存為新 revision，不覆寫歷史版本。"""

    for name, value in (("target_revision", target_revision), ("expected_revision", expected_revision)):
        if type(value) is not int or value < 1:
            raise PersonalUsePolicyError(f"{name} 必須是正整數")
    if not _is_sha256(target_policy_sha256):
        raise PersonalUsePolicyError("target_policy_sha256 格式無效")
    policy_path = _explicit_policy_path(path)
    with _interprocess_lock(policy_path):
        current_raw = _read_optional_bytes(policy_path)
        current_revision = _revision_from_bytes(current_raw, policy_path)
        if current_revision != expected_revision:
            raise PersonalUsePolicyConflict(
                f"個人設定版本衝突：expected={expected_revision}, current={current_revision}"
            )
        if target_revision >= current_revision:
            raise PersonalUsePolicyError("rollback 只能指定較早的 revision")
        historical_raw = _find_archived_revision(
            policy_path, target_revision, target_policy_sha256
        )
        historical = _decode_policy(historical_raw, policy_path)
        if (
            historical.revision != target_revision
            or historical.policy_sha256 != target_policy_sha256
        ):
            raise PersonalUsePolicyError("歷史版本 hash 不符")
        if current_raw is not None:
            _archive_revision(policy_path, current_raw)
        selection = RecommendationPersonalUseSelectionV1(
            scope_id=historical.scope_id,
            mode=historical.mode,
            candidate=historical.candidate,
        )
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        )
        return _write_new_revision(
            policy_path,
            selection,
            revision=current_revision + 1,
            confirmed_at=now,
            rollback_of_revision=target_revision,
            rollback_of_policy_sha256=target_policy_sha256,
        )


def save_personal_use_policy_v2(
    path: str | Path,
    selection: RecommendationPersonalUseSelectionV2,
    *,
    expected_revision: int,
) -> RecommendationPersonalUsePolicyV2:
    """以同一跨程序 revision CAS 保存已確認的 V2 個人選擇。"""

    if type(selection) is not RecommendationPersonalUseSelectionV2:
        raise TypeError("selection 必須是 RecommendationPersonalUseSelectionV2")
    if type(expected_revision) is not int or expected_revision < 0:
        raise PersonalUsePolicyError("expected_revision 必須是非負整數")
    policy_path = _explicit_policy_path(path)
    with _interprocess_lock(policy_path):
        current_raw = _read_optional_bytes(policy_path)
        current_revision = _revision_from_bytes(current_raw, policy_path)
        if current_revision != expected_revision:
            raise PersonalUsePolicyConflict(
                f"個人設定版本衝突：expected={expected_revision}, current={current_revision}"
            )
        if current_raw is not None:
            _archive_revision(policy_path, current_raw)
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        )
        return _write_new_revision_v2(
            policy_path,
            selection,
            revision=current_revision + 1,
            confirmed_at=now,
        )


def rollback_personal_use_policy_v2(
    path: str | Path,
    *,
    target_revision: int,
    target_policy_sha256: str,
    expected_revision: int,
    source_time_binding: PersonalSourceTimeBindingProposalV1 | None = None,
) -> RecommendationPersonalUsePolicyV2:
    """以新確認時間重建 V2 歷史選擇，並要求來源信任重新檢查。"""

    for name, value in (("target_revision", target_revision), ("expected_revision", expected_revision)):
        if type(value) is not int or value < 1:
            raise PersonalUsePolicyError(f"{name} 必須是正整數")
    if not _is_sha256(target_policy_sha256):
        raise PersonalUsePolicyError("target_policy_sha256 格式無效")
    if source_time_binding is not None and type(
        source_time_binding
    ) is not PersonalSourceTimeBindingProposalV1:
        raise PersonalUsePolicyError("V2 rollback 的來源時間提案型別無效")
    policy_path = _explicit_policy_path(path)
    with _interprocess_lock(policy_path):
        current_raw = _read_optional_bytes(policy_path)
        current_revision = _revision_from_bytes(current_raw, policy_path)
        if current_revision != expected_revision:
            raise PersonalUsePolicyConflict(
                f"個人設定版本衝突：expected={expected_revision}, current={current_revision}"
            )
        if target_revision >= current_revision:
            raise PersonalUsePolicyError("rollback 只能指定較早的 revision")
        historical_raw = _find_archived_revision(
            policy_path, target_revision, target_policy_sha256
        )
        historical = _decode_policy_snapshot(historical_raw, policy_path)
        if (
            type(historical) is not RecommendationPersonalUsePolicyV2
            or historical.revision != target_revision
            or historical.policy_sha256 != target_policy_sha256
        ):
            raise PersonalUsePolicyError("指定歷史版本不是相符的 V2 policy")
        if historical.mode == PERSONAL_CALIBRATED_PROBABILITY_MODE:
            if (
                historical.source_time_trust is None
                or source_time_binding is None
                or not _same_source_binding(historical.source_time_trust, source_time_binding)
            ):
                raise PersonalUsePolicyError("回退前必須重新確認相同來源切片與候選")
        elif source_time_binding is not None:
            raise PersonalUsePolicyError("rule_only V2 不接受回退時附帶模型來源信任")
        if current_raw is not None:
            _archive_revision(policy_path, current_raw)
        selection = RecommendationPersonalUseSelectionV2(
            scope_id=historical.scope_id,
            mode=historical.mode,
            source_time_binding=(
                source_time_binding
                if historical.mode == PERSONAL_CALIBRATED_PROBABILITY_MODE
                else None
            ),
        )
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        )
        return _write_new_revision_v2(
            policy_path,
            selection,
            revision=current_revision + 1,
            confirmed_at=now,
            rollback_of_revision=target_revision,
            rollback_of_policy_sha256=target_policy_sha256,
        )


def list_personal_use_policy_revisions(
    path: str | Path,
) -> tuple[RecommendationPersonalUsePolicyV1 | RecommendationPersonalUsePolicyV2, ...]:
    """列出已驗證歷史設定；V2 trust 仍須在回退/執行前重新檢查。"""

    policy_path = _explicit_policy_path(path)
    archive_dir = policy_path.with_name(f"{policy_path.name}.revisions")
    try:
        entries = tuple(archive_dir.iterdir())
    except FileNotFoundError:
        return ()
    except OSError as exc:
        raise PersonalUsePolicyError("無法列舉個人設定歷史版本") from exc
    revisions: list[RecommendationPersonalUsePolicyV1 | RecommendationPersonalUsePolicyV2] = []
    for archived_path in entries:
        if not archived_path.name.startswith("rev-") or archived_path.suffix != ".json":
            continue
        try:
            raw = archived_path.read_bytes()
        except OSError as exc:
            raise PersonalUsePolicyError("無法讀取個人設定歷史版本") from exc
        decoded = _decode_policy_snapshot(raw, policy_path)
        expected_name = (
            f"rev-{decoded.revision:08d}-{decoded.policy_sha256[7:]}.json"
        )
        if archived_path.name != expected_name:
            raise PersonalUsePolicyError("歷史版本檔名與內容身分不一致")
        revisions.append(decoded)
    return tuple(sorted(revisions, key=lambda item: item.revision))


def _write_new_revision(
    path: Path,
    selection: RecommendationPersonalUseSelectionV1,
    *,
    revision: int,
    confirmed_at: str,
    rollback_of_revision: int | None = None,
    rollback_of_policy_sha256: str | None = None,
) -> RecommendationPersonalUsePolicyV1:
    body: dict[str, Any] = {
        "schema_version": PERSONAL_USE_POLICY_SCHEMA_V1,
        "policy_version": PERSONAL_USE_POLICY_VERSION,
        "revision": revision,
        "scope_id": selection.scope_id,
        "mode": selection.mode,
        "confirmed_at": confirmed_at,
        "candidate": selection.candidate.to_dict() if selection.candidate is not None else None,
    }
    if rollback_of_revision is not None:
        body["rollback_of_revision"] = rollback_of_revision
        body["rollback_of_policy_sha256"] = rollback_of_policy_sha256
    digest = _policy_hash(body)
    payload = {**body, "policy_sha256": digest}
    raw = (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    _atomic_replace_bytes(path, raw)
    return _decode_policy(raw, path)


def _write_new_revision_v2(
    path: Path,
    selection: RecommendationPersonalUseSelectionV2,
    *,
    revision: int,
    confirmed_at: str,
    rollback_of_revision: int | None = None,
    rollback_of_policy_sha256: str | None = None,
) -> RecommendationPersonalUsePolicyV2:
    if selection.mode == RULE_ONLY_MODE and selection.source_time_binding is not None:
        raise PersonalUsePolicyError("rule_only 不可保存來源時間信任")
    if (
        selection.mode == PERSONAL_CALIBRATED_PROBABILITY_MODE
        and type(selection.source_time_binding) is not PersonalSourceTimeBindingProposalV1
    ):
        raise PersonalUsePolicyError("校準模式缺少來源時間檢查提案")
    trust = (
        PersonalSourceTimeTrustV1.from_proposal(
            _validated_proposal(selection.source_time_binding),
            confirmed_at=confirmed_at,
        )
        if selection.source_time_binding is not None
        else None
    )
    candidate = trust.candidate if trust is not None else None
    body: dict[str, Any] = {
        "schema_version": PERSONAL_USE_POLICY_SCHEMA_V2,
        "policy_version": PERSONAL_USE_POLICY_VERSION_V2,
        "revision": revision,
        "scope_id": selection.scope_id,
        "mode": selection.mode,
        "confirmed_at": confirmed_at,
        "candidate": candidate.to_dict() if candidate is not None else None,
        "source_time_trust": trust.to_dict() if trust is not None else None,
    }
    if rollback_of_revision is not None:
        body["rollback_of_revision"] = rollback_of_revision
        body["rollback_of_policy_sha256"] = rollback_of_policy_sha256
    digest = _policy_hash(body)
    payload = {**body, "policy_sha256": digest}
    raw = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    _atomic_replace_bytes(path, raw)
    return _decode_policy_v2(raw, path)


def _decode_policy(raw: bytes, path: Path) -> RecommendationPersonalUsePolicyV1:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PersonalUsePolicyError("個人設定檔不是有效 UTF-8 JSON") from exc
    if type(payload) is not dict:
        raise PersonalUsePolicyError("個人設定檔根節點必須是 object")
    expected = {
        "schema_version",
        "policy_version",
        "revision",
        "scope_id",
        "mode",
        "confirmed_at",
        "candidate",
        "policy_sha256",
    }
    optional = {"rollback_of_revision", "rollback_of_policy_sha256"}
    if set(payload) - optional != expected or set(payload) & optional not in (
        set(), optional
    ):
        raise PersonalUsePolicyError("個人設定檔欄位不符合 schema")
    if (
        payload.get("schema_version") != PERSONAL_USE_POLICY_SCHEMA_V1
        or type(payload.get("policy_version")) is not int
        or payload.get("policy_version") != PERSONAL_USE_POLICY_VERSION
        or type(payload.get("revision")) is not int
        or payload.get("revision", 0) < 1
    ):
        raise PersonalUsePolicyError("個人設定檔 schema/version/revision 無效")
    scope_id = payload.get("scope_id")
    mode = payload.get("mode")
    if type(scope_id) is not str or not _valid_scope_id(scope_id):
        raise PersonalUsePolicyError("scope_id 無效")
    if type(mode) is not str or mode not in PERSONAL_USE_MODES:
        raise PersonalUsePolicyError("個人設定模式無效")
    confirmed_at = payload.get("confirmed_at")
    if type(confirmed_at) is not str or not _aware_utc_timestamp(confirmed_at):
        raise PersonalUsePolicyError("confirmed_at 必須是 aware UTC timestamp")
    candidate_payload = payload.get("candidate")
    candidate = _decode_candidate(candidate_payload) if candidate_payload is not None else None
    if mode == "personal_calibrated_probability" and candidate is None:
        raise PersonalUsePolicyError("個人校準模式缺少 pinned candidate")
    rollback_revision = payload.get("rollback_of_revision")
    rollback_hash = payload.get("rollback_of_policy_sha256")
    if (rollback_revision is None) != (rollback_hash is None):
        raise PersonalUsePolicyError("rollback provenance 欄位不完整")
    if rollback_revision is not None and (
        type(rollback_revision) is not int
        or rollback_revision < 1
        or rollback_revision >= payload["revision"]
        or not _is_sha256(rollback_hash)
    ):
        raise PersonalUsePolicyError("rollback provenance 無效")
    declared_hash = payload.get("policy_sha256")
    body = {key: value for key, value in payload.items() if key != "policy_sha256"}
    actual_hash = _policy_hash(body)
    if declared_hash != actual_hash:
        raise PersonalUsePolicyError("policy_sha256 不符")
    return RecommendationPersonalUsePolicyV1(
        revision=payload["revision"],
        scope_id=scope_id,
        mode=mode,
        confirmed_at=confirmed_at,
        candidate=candidate,
        policy_sha256=actual_hash,
        storage_path=path,
        storage_bytes=raw,
        rollback_of_revision=rollback_revision,
        rollback_of_policy_sha256=rollback_hash,
    )


def _decode_policy_snapshot(
    raw: bytes, path: Path
) -> RecommendationPersonalUsePolicyV1 | RecommendationPersonalUsePolicyV2:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PersonalUsePolicyError("個人設定檔不是有效 UTF-8 JSON") from exc
    if type(payload) is not dict:
        raise PersonalUsePolicyError("個人設定檔根節點必須是 object")
    schema = payload.get("schema_version")
    if schema == PERSONAL_USE_POLICY_SCHEMA_V1:
        return _decode_policy(raw, path)
    if schema == PERSONAL_USE_POLICY_SCHEMA_V2:
        return _decode_policy_v2(raw, path)
    raise PersonalUsePolicyError("不支援的個人設定 schema_version")


def _decode_policy_v2(raw: bytes, path: Path) -> RecommendationPersonalUsePolicyV2:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PersonalUsePolicyError("個人設定檔不是有效 UTF-8 JSON") from exc
    if type(payload) is not dict:
        raise PersonalUsePolicyError("個人設定檔根節點必須是 object")
    expected = {
        "schema_version",
        "policy_version",
        "revision",
        "scope_id",
        "mode",
        "confirmed_at",
        "candidate",
        "source_time_trust",
        "policy_sha256",
    }
    optional = {"rollback_of_revision", "rollback_of_policy_sha256"}
    if set(payload) - optional != expected or set(payload) & optional not in (set(), optional):
        raise PersonalUsePolicyError("V2 個人設定檔欄位不符合 schema")
    if (
        payload.get("schema_version") != PERSONAL_USE_POLICY_SCHEMA_V2
        or type(payload.get("policy_version")) is not int
        or payload.get("policy_version") != PERSONAL_USE_POLICY_VERSION_V2
        or type(payload.get("revision")) is not int
        or payload.get("revision", 0) < 1
    ):
        raise PersonalUsePolicyError("V2 個人設定 schema/version/revision 無效")
    scope_id = payload.get("scope_id")
    mode = payload.get("mode")
    if type(scope_id) is not str or not _valid_scope_id(scope_id):
        raise PersonalUsePolicyError("scope_id 無效")
    if type(mode) is not str or mode not in PERSONAL_USE_MODES:
        raise PersonalUsePolicyError("個人設定模式無效")
    confirmed_at = payload.get("confirmed_at")
    if type(confirmed_at) is not str or not _aware_utc_timestamp(confirmed_at):
        raise PersonalUsePolicyError("confirmed_at 必須是 aware UTC timestamp")
    candidate_payload = payload.get("candidate")
    candidate = _decode_candidate(candidate_payload) if candidate_payload is not None else None
    trust_payload = payload.get("source_time_trust")
    trust = _decode_source_time_trust(trust_payload) if trust_payload is not None else None
    if mode == PERSONAL_CALIBRATED_PROBABILITY_MODE:
        if candidate is None or trust is None:
            raise PersonalUsePolicyError("V2 個人校準模式缺少來源信任或候選 pins")
        if candidate != trust.candidate:
            raise PersonalUsePolicyError("V2 頂層候選與 source_time_trust pins 不一致")
        if trust.confirmed_at != confirmed_at:
            raise PersonalUsePolicyError("policy/source trust 確認時間不一致")
    elif candidate is not None or trust is not None:
        raise PersonalUsePolicyError("V2 rule_only 必須清除候選與來源信任")
    rollback_revision = payload.get("rollback_of_revision")
    rollback_hash = payload.get("rollback_of_policy_sha256")
    if (rollback_revision is None) != (rollback_hash is None):
        raise PersonalUsePolicyError("rollback provenance 欄位不完整")
    if rollback_revision is not None and (
        type(rollback_revision) is not int
        or rollback_revision < 1
        or rollback_revision >= payload["revision"]
        or not _is_sha256(rollback_hash)
    ):
        raise PersonalUsePolicyError("rollback provenance 無效")
    declared_hash = payload.get("policy_sha256")
    body = {key: value for key, value in payload.items() if key != "policy_sha256"}
    actual_hash = _policy_hash(body)
    if declared_hash != actual_hash:
        raise PersonalUsePolicyError("policy_sha256 不符")
    return RecommendationPersonalUsePolicyV2(
        revision=payload["revision"],
        scope_id=scope_id,
        mode=mode,
        confirmed_at=confirmed_at,
        candidate=candidate,
        source_time_trust=trust,
        policy_sha256=actual_hash,
        storage_path=path,
        storage_bytes=raw,
        rollback_of_revision=rollback_revision,
        rollback_of_policy_sha256=rollback_hash,
    )


def _validate_source_binding_fields(
    *,
    schema_version: str,
    expected_schema: str,
    basis: str,
    source_database_path: str,
    file_identity: PersonalSourceFileIdentityV1,
    source_database_size_bytes: int,
    source_slice_sha256: str,
    candidate: PersonalCalibrationCandidateV1,
    replay_scope: PersonalSourceReplayScopeV1,
    research_only: bool,
    official_historical_pit_verified: bool,
) -> None:
    if schema_version != expected_schema:
        raise PersonalUsePolicyError("source-time binding schema_version 無效")
    if basis != "user_declared_source_time":
        raise PersonalUsePolicyError("source-time binding basis 無效")
    if type(source_database_path) is not str or not source_database_path.strip():
        raise PersonalUsePolicyError("source_database_path 不可為空")
    if not Path(source_database_path).is_absolute() or ".." in Path(source_database_path).parts:
        raise PersonalUsePolicyError("source_database_path 必須是明確絕對路徑")
    if type(file_identity) is not PersonalSourceFileIdentityV1:
        raise PersonalUsePolicyError("file_identity 型別無效")
    if type(source_database_size_bytes) is not int or source_database_size_bytes < 0:
        raise PersonalUsePolicyError("source_database_size_bytes 必須是非負整數")
    if not _is_sha256(source_slice_sha256):
        raise PersonalUsePolicyError("source_slice_sha256 格式無效")
    if type(candidate) is not PersonalCalibrationCandidateV1:
        raise PersonalUsePolicyError("source-time candidate pins 型別無效")
    if type(replay_scope) is not PersonalSourceReplayScopeV1:
        raise PersonalUsePolicyError("replay_scope 型別無效")
    if type(research_only) is not bool or not research_only:
        raise PersonalUsePolicyError("user-declared source-time 只能是 research_only")
    if type(official_historical_pit_verified) is not bool or official_historical_pit_verified:
        raise PersonalUsePolicyError("user-declared source-time 不得標記 official PIT verified")


def _decode_source_binding_proposal(value: Any) -> PersonalSourceTimeBindingProposalV1:
    if type(value) is not dict:
        raise PersonalUsePolicyError("source_time_binding 必須是 object")
    expected = {
        "schema_version",
        "basis",
        "source_database_path",
        "file_identity",
        "source_database_size_bytes",
        "source_slice_sha256",
        "candidate",
        "replay_scope",
        "research_only",
        "official_historical_pit_verified",
    }
    if set(value) != expected:
        raise PersonalUsePolicyError("source-time proposal 欄位不符合 schema")
    return PersonalSourceTimeBindingProposalV1(
        schema_version=value["schema_version"],
        basis=value["basis"],
        source_database_path=value["source_database_path"],
        file_identity=_decode_file_identity(value["file_identity"]),
        source_database_size_bytes=value["source_database_size_bytes"],
        source_slice_sha256=value["source_slice_sha256"],
        candidate=_decode_candidate(value["candidate"]),
        replay_scope=_decode_replay_scope(value["replay_scope"]),
        research_only=value["research_only"],
        official_historical_pit_verified=value["official_historical_pit_verified"],
    )


def _decode_source_time_trust(value: Any) -> PersonalSourceTimeTrustV1:
    if type(value) is not dict:
        raise PersonalUsePolicyError("source_time_trust 必須是 object")
    expected = {
        "schema_version",
        "basis",
        "confirmed_at",
        "source_database_path",
        "file_identity",
        "source_database_size_bytes",
        "source_slice_sha256",
        "candidate",
        "replay_scope",
        "research_only",
        "official_historical_pit_verified",
    }
    if set(value) != expected:
        raise PersonalUsePolicyError("source_time_trust 欄位不符合 schema")
    return PersonalSourceTimeTrustV1(
        schema_version=value["schema_version"],
        basis=value["basis"],
        confirmed_at=value["confirmed_at"],
        source_database_path=value["source_database_path"],
        file_identity=_decode_file_identity(value["file_identity"]),
        source_database_size_bytes=value["source_database_size_bytes"],
        source_slice_sha256=value["source_slice_sha256"],
        candidate=_decode_candidate(value["candidate"]),
        replay_scope=_decode_replay_scope(value["replay_scope"]),
        research_only=value["research_only"],
        official_historical_pit_verified=value["official_historical_pit_verified"],
    )


def _decode_file_identity(value: Any) -> PersonalSourceFileIdentityV1:
    if type(value) is not dict or set(value) != {"device", "inode"}:
        raise PersonalUsePolicyError("file_identity 欄位不符合 schema")
    return PersonalSourceFileIdentityV1(device=value["device"], inode=value["inode"])


def _decode_replay_scope(value: Any) -> PersonalSourceReplayScopeV1:
    expected = {"dataset_ids", "decision_dates", "symbols", "sample_count"}
    if type(value) is not dict or set(value) != expected:
        raise PersonalUsePolicyError("replay_scope 欄位不符合 schema")
    list_fields: dict[str, tuple[str, ...]] = {}
    for name in ("dataset_ids", "decision_dates", "symbols"):
        raw = value[name]
        if type(raw) is not list:
            raise PersonalUsePolicyError(f"replay_scope.{name} 必須是 JSON array")
        list_fields[name] = tuple(raw)
    return PersonalSourceReplayScopeV1(
        dataset_ids=list_fields["dataset_ids"],
        decision_dates=list_fields["decision_dates"],
        symbols=list_fields["symbols"],
        sample_count=value["sample_count"],
    )


def _validated_proposal(
    proposal: PersonalSourceTimeBindingProposalV1 | None,
) -> PersonalSourceTimeBindingProposalV1:
    if type(proposal) is not PersonalSourceTimeBindingProposalV1:
        raise PersonalUsePolicyError("source_time_binding 必須是已檢查的 proposal DTO")
    return _decode_source_binding_proposal(proposal.to_dict())


def _same_source_binding(
    trust: PersonalSourceTimeTrustV1,
    proposal: PersonalSourceTimeBindingProposalV1,
) -> bool:
    validated = _validated_proposal(proposal)
    return (
        trust.source_database_path == validated.source_database_path
        and trust.file_identity == validated.file_identity
        and trust.source_slice_sha256 == validated.source_slice_sha256
        and trust.candidate == validated.candidate
        and trust.replay_scope == validated.replay_scope
    )


def _decode_candidate(value: Any) -> PersonalCalibrationCandidateV1:
    if type(value) is not dict:
        raise PersonalUsePolicyError("candidate 必須是 object")
    keys = {
        "candidate_id",
        "candidate_root",
        "candidate_json_sha256",
        "candidate_manifest_hash",
        "candidate_artifact_hash",
        "candidate_freeze_hash",
        "dataset_hash",
    }
    if set(value) != keys or any(type(item) is not str for item in value.values()):
        raise PersonalUsePolicyError("candidate identity 欄位不完整或型別錯誤")
    return PersonalCalibrationCandidateV1(**value)


def _revision_from_bytes(raw: bytes | None, path: Path) -> int:
    if raw is None:
        return 0
    return _decode_policy_snapshot(raw, path).revision


def _read_optional_bytes(path: Path) -> bytes | None:
    if path.is_symlink():
        raise PersonalUsePolicyError("個人設定檔不可是 symlink")
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _archive_revision(path: Path, raw: bytes) -> None:
    current = _decode_policy_snapshot(raw, path)
    archive_dir = path.with_name(f"{path.name}.revisions")
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"rev-{current.revision:08d}-{current.policy_sha256[7:]}.json"
    try:
        with archive_path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        if archive_path.read_bytes() != raw:
            raise PersonalUsePolicyConflict("歷史 revision 路徑已有不同 bytes")


def _find_archived_revision(path: Path, revision: int, digest: str) -> bytes:
    archive_path = path.with_name(f"{path.name}.revisions") / (
        f"rev-{revision:08d}-{digest[7:]}.json"
    )
    try:
        return archive_path.read_bytes()
    except OSError as exc:
        raise PersonalUsePolicyError("指定歷史 revision 不存在") from exc


def _atomic_replace_bytes(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise PersonalUsePolicyError("個人設定檔不可是 symlink")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


@contextmanager
def _interprocess_lock(path: Path, *, timeout_seconds: float = 10.0) -> Iterator[None]:
    """用穩定 sidecar OS lock 序列化 CAS；不依賴 PID 猜測。"""

    lock_path = path.with_name(f".{path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:  # pragma: no cover - exercised on POSIX CI only
                    import fcntl

                    posix_lock = cast(_PosixFileLockAPI, fcntl)
                    posix_lock.flock(
                        handle.fileno(), posix_lock.LOCK_EX | posix_lock.LOCK_NB
                    )
                locked = True
                break
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"個人設定 CAS lock timeout: {path}")
                time.sleep(0.05)
        try:
            yield
        finally:
            if locked:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:  # pragma: no cover - exercised on POSIX CI only
                    import fcntl

                    posix_lock = cast(_PosixFileLockAPI, fcntl)
                    posix_lock.flock(handle.fileno(), posix_lock.LOCK_UN)
    finally:
        handle.close()


def _explicit_policy_path(value: str | Path) -> Path:
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise PersonalUsePolicyError("必須明確指定個人設定檔路徑")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise PersonalUsePolicyError("個人設定檔路徑必須是絕對路徑")
    if path.is_symlink():
        raise PersonalUsePolicyError("個人設定檔不可是 symlink")
    return path.parent.resolve() / path.name


def _policy_hash(body: Mapping[str, Any]) -> str:
    raw = json.dumps(
        dict(body), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _is_sha256(value: Any) -> bool:
    return (
        type(value) is str
        and len(value) == 71
        and value.startswith("sha256:")
        and all(char in "0123456789abcdef" for char in value[7:])
    )


def _valid_scope_id(value: str) -> bool:
    return bool(value) and value.isascii() and all(
        char.isalnum() or char in "-_." for char in value
    )


def _aware_utc_timestamp(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        return False
    canonical = parsed.astimezone(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")
    return value == canonical
