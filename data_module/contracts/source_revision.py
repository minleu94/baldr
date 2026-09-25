"""跨資料來源修訂證據的純、不可變契約。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
import hashlib
import json
import re
from typing import TypeVar, cast


SOURCE_REVISION_EVIDENCE_SCHEMA_V1 = "validated-source-evidence.v1"


class SourceEvidenceNamespaceV1(str, Enum):
    """R026 必須明確檢查的四個來源修訂 namespace。"""

    MARKET_REVISION = "market_revision"
    HISTORICAL_SESSION_REVISION = "historical_session_revision"
    EXCLUDED_DAILY_PRICE_REVISION = "excluded_daily_price_revision"
    DAILY_PRICE_REPAIR_RECEIPT = "daily_price_repair_receipt"


SOURCE_EVIDENCE_NAMESPACE_ORDER_V1 = (
    SourceEvidenceNamespaceV1.MARKET_REVISION,
    SourceEvidenceNamespaceV1.HISTORICAL_SESSION_REVISION,
    SourceEvidenceNamespaceV1.EXCLUDED_DAILY_PRICE_REVISION,
    SourceEvidenceNamespaceV1.DAILY_PRICE_REPAIR_RECEIPT,
)


class SourceEvidencePresenceV1(str, Enum):
    """區分經完整檢查後的有證據與明確空集合。"""

    EMPTY = "empty"
    PRESENT = "present"


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SCOPE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_ROLE_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.-]*(?:/[A-Za-z0-9][A-Za-z0-9_.-]*)*$"
)
_T = TypeVar("_T")


def _require_sha256(value: str, field_name: str) -> None:
    if type(value) is not str or _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} 必須是 64 個小寫十六進位字元的 SHA-256")


def _require_role_id(value: str, field_name: str) -> None:
    if type(value) is not str:
        raise TypeError(f"{field_name} 必須是字串")
    if _ROLE_ID_PATTERN.fullmatch(value) is None:
        raise ValueError(
            f"{field_name} 必須是僅含 ASCII 安全字元的相對 POSIX role ID"
        )


def _freeze_records(
    value: tuple[object, ...] | list[object],
    *,
    expected_type: type[_T],
    field_name: str,
) -> tuple[_T, ...]:
    if not isinstance(value, (tuple, list)):
        raise TypeError(f"{field_name} 必須是 tuple 或 list")
    items = tuple(value)
    if any(type(item) is not expected_type for item in items):
        raise TypeError(f"{field_name} 含有不支援的 record 類型")
    return cast(tuple[_T, ...], items)


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def validate_source_evidence_identity_v1(
    *, scope_id: object, cutoff_date: object
) -> None:
    """使用 source-evidence contract 的共同路徑預先驗證 scope 與 cutoff。"""

    if (
        type(scope_id) is not str
        or _SCOPE_ID_PATTERN.fullmatch(scope_id) is None
    ):
        raise ValueError("scope_id 必須是穩定且非路徑的 ASCII 識別碼")
    if type(cutoff_date) is not date:
        raise TypeError("cutoff_date 必須是 date，不得是 datetime")


@dataclass(frozen=True, slots=True)
class ValidatedEvidenceFileV1:
    """記錄單次檢查實際讀取之單一 bytes buffer 的相對角色與 SHA-256。

    該 buffer 可由 namespace 既有 JSON 解析，或由已比對的 hash-link 驗證；
    本 record 不宣稱跨檔讀取具原子性。
    """

    role_id: str
    sha256: str

    def __post_init__(self) -> None:
        _require_role_id(self.role_id, "role_id")
        _require_sha256(self.sha256, "sha256")


@dataclass(frozen=True, slots=True)
class ValidatedNamespaceEvidenceV1:
    """單一 namespace 的不可變檔案證據；空集合明確記錄且不代表跨檔原子性。"""

    namespace: SourceEvidenceNamespaceV1
    presence: SourceEvidencePresenceV1
    files: tuple[ValidatedEvidenceFileV1, ...]

    def __post_init__(self) -> None:
        if type(self.namespace) is not SourceEvidenceNamespaceV1:
            raise TypeError("namespace 必須是已知的 SourceEvidenceNamespaceV1")
        if type(self.presence) is not SourceEvidencePresenceV1:
            raise TypeError("presence 必須是 SourceEvidencePresenceV1")
        frozen_files = _freeze_records(
            self.files,
            expected_type=ValidatedEvidenceFileV1,
            field_name="files",
        )
        role_ids = tuple(item.role_id for item in frozen_files)
        if len(role_ids) != len(set(role_ids)):
            raise ValueError("同一 namespace 的 role_id 不可重複")
        if role_ids != tuple(sorted(role_ids)):
            frozen_files = tuple(sorted(frozen_files, key=lambda item: item.role_id))
        if self.presence is SourceEvidencePresenceV1.EMPTY and frozen_files:
            raise ValueError("empty namespace 不得包含 evidence file")
        if self.presence is SourceEvidencePresenceV1.PRESENT and not frozen_files:
            raise ValueError("present namespace 必須包含 evidence file")
        object.__setattr__(self, "files", frozen_files)

    @property
    def digest_sha256(self) -> str:
        """回傳 namespace 內容摘要；scope 與 cutoff 由外層契約綁定。"""

        return _canonical_sha256(
            {
                "schema_version": SOURCE_REVISION_EVIDENCE_SCHEMA_V1,
                "namespace": self.namespace.value,
                "presence": self.presence.value,
                "files": [
                    {"role_id": item.role_id, "sha256": item.sha256}
                    for item in self.files
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class ValidatedSourceEvidenceV1:
    """固定四個 namespace、scope 與 PIT cutoff 的完整來源修訂摘要。"""

    schema_version: str
    scope_id: str
    cutoff_date: date
    namespaces: tuple[ValidatedNamespaceEvidenceV1, ...]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not str:
            raise TypeError("schema_version 必須是字串")
        if self.schema_version != SOURCE_REVISION_EVIDENCE_SCHEMA_V1:
            raise ValueError("不支援的 source evidence schema_version")
        validate_source_evidence_identity_v1(
            scope_id=self.scope_id,
            cutoff_date=self.cutoff_date,
        )

        frozen_namespaces = _freeze_records(
            self.namespaces,
            expected_type=ValidatedNamespaceEvidenceV1,
            field_name="namespaces",
        )
        namespace_ids = tuple(item.namespace for item in frozen_namespaces)
        if len(namespace_ids) != len(set(namespace_ids)):
            raise ValueError("namespace 不可重複")
        if set(namespace_ids) != set(SOURCE_EVIDENCE_NAMESPACE_ORDER_V1):
            raise ValueError("必須明確提供全部四個 source evidence namespace")
        ordered = tuple(
            sorted(
                frozen_namespaces,
                key=lambda item: SOURCE_EVIDENCE_NAMESPACE_ORDER_V1.index(
                    item.namespace
                ),
            )
        )
        object.__setattr__(self, "namespaces", ordered)

    @property
    def digest_sha256(self) -> str:
        """回傳綁定 schema、scope、cutoff 與四個 namespace 的 canonical hash。"""

        return _canonical_sha256(
            {
                "schema_version": self.schema_version,
                "scope_id": self.scope_id,
                "cutoff_date": self.cutoff_date.isoformat(),
                "namespaces": [
                    {
                        "namespace": item.namespace.value,
                        "presence": item.presence.value,
                        "digest_sha256": item.digest_sha256,
                    }
                    for item in self.namespaces
                ],
            }
        )
