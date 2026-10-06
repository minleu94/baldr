"""Live calibration invocation 的非持久來源身分組合事實。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import re
from typing import Literal

from app_module.recommendation.historical_snapshot_custody import (
    HistoricalRawSnapshotCustodyFactsV1,
    HistoricalRawSnapshotQueryScopeV1,
    build_historical_raw_snapshot_custody_facts_v1,
)
from data_module.contracts.source_revision import (
    SOURCE_REVISION_EVIDENCE_SCHEMA_V1,
    ValidatedSourceEvidenceV1,
)
from data_module.ml_historical_snapshot_provider import (
    HISTORICAL_SNAPSHOT_PROVIDER_CONTRACT_ID_V1,
    HistoricalRawSnapshot,
    ValidatedHistoricalLoadScopeV1,
)


LIVE_CALIBRATION_SOURCE_IDENTITY_SCHEMA_V1 = "live-calibration-source-identity.v1"
_LEASE_CHECK_KIND: Literal["same_connection_assert_unchanged_returned"] = (
    "same_connection_assert_unchanged_returned"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _sha256_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _require_digest(value: object, field_name: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return value


def _require_scope_id(value: object) -> str:
    if (
        type(value) is not str
        or not value.startswith("recommendation-live-")
        or len(value) != len("recommendation-live-") + 32
        or any(character not in "0123456789abcdef" for character in value[-32:])
    ):
        raise ValueError("scope_id must be an invocation-local live recommendation ID")
    return value


@dataclass(frozen=True, slots=True)
class SQLiteReadLeaseObservationV1:
    """記錄呼叫端同一連線 postcheck 已返回；不代表 durable generation。"""

    provider_contract_id: str
    scope_id: str
    check_kind: Literal["same_connection_assert_unchanged_returned"] = (
        _LEASE_CHECK_KIND
    )

    def __post_init__(self) -> None:
        if self.provider_contract_id != HISTORICAL_SNAPSHOT_PROVIDER_CONTRACT_ID_V1:
            raise ValueError("lease observation provider contract ID mismatch")
        _require_scope_id(self.scope_id)
        if self.check_kind != _LEASE_CHECK_KIND:
            raise ValueError("unsupported SQLite lease observation kind")


@dataclass(frozen=True, slots=True)
class LiveCalibrationSourceIdentityV1:
    """同一次 live call 的 rows、sidecar 與 lease observation 分欄組合。"""

    scope_id: str
    provider_contract_id: str
    decision_date: date
    history_start_date: date
    symbols: tuple[str, ...]
    raw_snapshot: HistoricalRawSnapshotCustodyFactsV1
    sidecar_evidence: ValidatedSourceEvidenceV1
    sidecar_before_digest_sha256: str
    sqlite_lease_observation: SQLiteReadLeaseObservationV1

    def __post_init__(self) -> None:
        _require_scope_id(self.scope_id)
        if self.provider_contract_id != HISTORICAL_SNAPSHOT_PROVIDER_CONTRACT_ID_V1:
            raise ValueError("live identity provider contract ID mismatch")
        if type(self.decision_date) is not date or type(self.history_start_date) is not date:
            raise TypeError("live identity dates must be exact date values")
        if self.history_start_date >= self.decision_date:
            raise ValueError("live identity history start must precede decision date")
        if type(self.symbols) is not tuple or not self.symbols:
            raise TypeError("live identity symbols must be a non-empty tuple")
        if any(
            type(symbol) is not str or not symbol or symbol != symbol.strip()
            for symbol in self.symbols
        ):
            raise ValueError("live identity symbols must be normalized text")
        if tuple(sorted(set(self.symbols))) != self.symbols:
            raise ValueError("live identity symbols must be sorted and unique")
        if type(self.raw_snapshot) is not HistoricalRawSnapshotCustodyFactsV1:
            raise TypeError("raw_snapshot must be same-call custody facts")
        if type(self.sidecar_evidence) is not ValidatedSourceEvidenceV1:
            raise TypeError("sidecar_evidence must be validated four-namespace evidence")
        if self.sidecar_evidence.schema_version != SOURCE_REVISION_EVIDENCE_SCHEMA_V1:
            raise ValueError("sidecar evidence schema version mismatch")
        if self.sidecar_evidence.scope_id != self.scope_id:
            raise ValueError("sidecar evidence scope ID mismatch")
        if self.sidecar_evidence.cutoff_date != self.decision_date:
            raise ValueError("sidecar evidence cutoff mismatch")
        _require_digest(self.sidecar_before_digest_sha256, "sidecar_before_digest_sha256")
        if self.sidecar_before_digest_sha256 != self.sidecar_evidence.digest_sha256:
            raise ValueError("before/after sidecar evidence digest mismatch")
        if type(self.sqlite_lease_observation) is not SQLiteReadLeaseObservationV1:
            raise TypeError("sqlite_lease_observation must be an exact lease observation")
        if (
            self.sqlite_lease_observation.scope_id != self.scope_id
            or self.sqlite_lease_observation.provider_contract_id
            != self.provider_contract_id
        ):
            raise ValueError("SQLite lease observation identity mismatch")
        raw_scope = self.raw_snapshot.query_scope
        if (
            raw_scope.source_id != self.provider_contract_id
            or raw_scope.decision_date != self.decision_date
            or raw_scope.history_start_date != self.history_start_date
            or raw_scope.symbols != self.symbols
        ):
            raise ValueError("raw snapshot custody identity mismatch")

    @property
    def identity_digest_sha256(self) -> str:
        """回傳 shadow join digest；不可用作 `source_revision` 或持久 revision。"""

        return _sha256_json(
            {
                "schema_version": LIVE_CALIBRATION_SOURCE_IDENTITY_SCHEMA_V1,
                "scope_id": self.scope_id,
                "provider_contract_id": self.provider_contract_id,
                "decision_date": self.decision_date.isoformat(),
                "history_start_date": self.history_start_date.isoformat(),
                "symbols": list(self.symbols),
                "raw_snapshot_id": self.raw_snapshot.snapshot_id,
                "raw_content_hash": self.raw_snapshot.content_hash,
                "raw_row_identity_hash": self.raw_snapshot.row_identity_hash,
                "sidecar_digest_sha256": self.sidecar_evidence.digest_sha256,
                "sqlite_lease_check": self.sqlite_lease_observation.check_kind,
            }
        )


def compose_live_calibration_source_identity_v1(
    *,
    snapshot: HistoricalRawSnapshot,
    query_scope: HistoricalRawSnapshotQueryScopeV1,
    source_evidence_before: ValidatedSourceEvidenceV1,
    source_evidence_after: ValidatedSourceEvidenceV1,
    sqlite_lease_observation: SQLiteReadLeaseObservationV1,
) -> LiveCalibrationSourceIdentityV1:
    """純組合同次 provider snapshot、sidecar evidence 與 lease postcheck。"""

    if type(snapshot) is not HistoricalRawSnapshot:
        raise TypeError("snapshot must be HistoricalRawSnapshot")
    if snapshot.provider_contract_id != HISTORICAL_SNAPSHOT_PROVIDER_CONTRACT_ID_V1:
        raise ValueError("provider-carried historical source contract ID is required")
    if type(query_scope) is not HistoricalRawSnapshotQueryScopeV1:
        raise TypeError("query_scope must be HistoricalRawSnapshotQueryScopeV1")
    if query_scope.source_id != snapshot.provider_contract_id:
        raise ValueError("query scope source ID does not match provider contract ID")
    if type(source_evidence_before) is not ValidatedSourceEvidenceV1 or type(
        source_evidence_after
    ) is not ValidatedSourceEvidenceV1:
        raise TypeError("before/after evidence must be exact validated aggregates")
    if source_evidence_before != source_evidence_after:
        raise ValueError("sidecar source evidence changed within invocation")
    if (
        source_evidence_before.schema_version != SOURCE_REVISION_EVIDENCE_SCHEMA_V1
        or source_evidence_before.scope_id != sqlite_lease_observation.scope_id
        or source_evidence_before.cutoff_date != query_scope.decision_date
    ):
        raise ValueError("sidecar evidence does not match live query scope")
    request = snapshot.validated_query_scope
    if type(request) is not ValidatedHistoricalLoadScopeV1:
        raise ValueError("same-call provider query evidence is required")
    if (
        request.decision_date != query_scope.decision_date.isoformat()
        or request.history_start_date != query_scope.history_start_date.isoformat()
        or request.symbols != query_scope.symbols
        or request.industry_index_names != query_scope.industry_index_names
    ):
        raise ValueError("custody query scope differs from same-call provider request")
    if snapshot.decision_date != query_scope.decision_date.isoformat():
        raise ValueError("lease/provider identity differs from same-call snapshot")

    custody = build_historical_raw_snapshot_custody_facts_v1(
        snapshot=snapshot,
        query_scope=query_scope,
    )
    return LiveCalibrationSourceIdentityV1(
        scope_id=source_evidence_before.scope_id,
        provider_contract_id=snapshot.provider_contract_id,
        decision_date=query_scope.decision_date,
        history_start_date=query_scope.history_start_date,
        symbols=query_scope.symbols,
        raw_snapshot=custody,
        sidecar_evidence=source_evidence_after,
        sidecar_before_digest_sha256=source_evidence_before.digest_sha256,
        sqlite_lease_observation=sqlite_lease_observation,
    )
