from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date, datetime, timezone
import hashlib

import pytest

from data_module.contracts import (
    SOURCE_EVIDENCE_NAMESPACE_ORDER_V1,
    SOURCE_REVISION_EVIDENCE_SCHEMA_V1,
    SourceEvidenceNamespaceV1,
    SourceEvidencePresenceV1,
    ValidatedEvidenceFileV1,
    ValidatedNamespaceEvidenceV1,
    ValidatedSourceEvidenceV1,
)


def _file(role_id: str, payload: str) -> ValidatedEvidenceFileV1:
    return ValidatedEvidenceFileV1(
        role_id=role_id,
        sha256=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    )


def _namespace(
    namespace: SourceEvidenceNamespaceV1,
    files: list[ValidatedEvidenceFileV1] | tuple[ValidatedEvidenceFileV1, ...] = (),
) -> ValidatedNamespaceEvidenceV1:
    return ValidatedNamespaceEvidenceV1(
        namespace=namespace,
        presence=(
            SourceEvidencePresenceV1.PRESENT
            if files
            else SourceEvidencePresenceV1.EMPTY
        ),
        files=files,  # type: ignore[arg-type]
    )


def _complete_namespaces() -> list[ValidatedNamespaceEvidenceV1]:
    return [
        _namespace(namespace)
        for namespace in SOURCE_EVIDENCE_NAMESPACE_ORDER_V1
    ]


def _source(
    namespaces: list[ValidatedNamespaceEvidenceV1]
    | tuple[ValidatedNamespaceEvidenceV1, ...]
    | None = None,
    *,
    scope_id: str = "synthetic-market-db",
    cutoff_date: date = date(2024, 1, 22),
    schema_version: str = SOURCE_REVISION_EVIDENCE_SCHEMA_V1,
) -> ValidatedSourceEvidenceV1:
    return ValidatedSourceEvidenceV1(
        schema_version=schema_version,
        scope_id=scope_id,
        cutoff_date=cutoff_date,
        namespaces=_complete_namespaces() if namespaces is None else namespaces,  # type: ignore[arg-type]
    )


def test_contract_copies_mutable_inputs_and_records_are_frozen() -> None:
    file_records = [_file("runs/repair/receipt.json", "receipt-v1")]
    namespace = _namespace(
        SourceEvidenceNamespaceV1.DAILY_PRICE_REPAIR_RECEIPT,
        file_records,
    )
    namespace_records = [
        namespace,
        *[
            _namespace(value)
            for value in SOURCE_EVIDENCE_NAMESPACE_ORDER_V1
            if value is not namespace.namespace
        ],
    ]
    source = _source(namespace_records)
    original_digest = source.digest_sha256

    file_records.clear()
    namespace_records.clear()

    assert len(namespace.files) == 1
    assert len(source.namespaces) == 4
    assert source.digest_sha256 == original_digest
    with pytest.raises(FrozenInstanceError):
        source.scope_id = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        namespace.files[0].sha256 = "0" * 64  # type: ignore[misc]
    assert not hasattr(source, "__dict__")


def test_explicit_empty_is_distinct_from_missing_or_present_evidence() -> None:
    empty = _source()
    with_present_file = _complete_namespaces()
    with_present_file[0] = _namespace(
        SOURCE_EVIDENCE_NAMESPACE_ORDER_V1[0],
        [_file("revision/marker.json", "marker-v1")],
    )
    present = _source(with_present_file)

    assert len(empty.namespaces) == 4
    assert all(
        item.presence is SourceEvidencePresenceV1.EMPTY
        for item in empty.namespaces
    )
    assert empty.digest_sha256 != present.digest_sha256
    with pytest.raises(ValueError, match="全部四個"):
        _source(_complete_namespaces()[:-1])


def test_namespace_and_file_inputs_are_canonicalized_and_digest_is_stable() -> None:
    files = [
        _file("runs/z/receipt.json", "z"),
        _file("runs/a/plan.json", "a"),
    ]
    namespace = ValidatedNamespaceEvidenceV1(
        namespace=SourceEvidenceNamespaceV1.MARKET_REVISION,
        presence=SourceEvidencePresenceV1.PRESENT,
        files=files,  # type: ignore[arg-type]
    )
    namespaces = [namespace, *_complete_namespaces()[1:]]
    first = _source(namespaces)
    second = _source(list(reversed(namespaces)))

    assert tuple(item.role_id for item in first.namespaces[0].files) == (
        "runs/a/plan.json",
        "runs/z/receipt.json",
    )
    assert first.digest_sha256 == second.digest_sha256
    assert first.digest_sha256 == _source(namespaces).digest_sha256
    assert len(first.digest_sha256) == 64
    assert first.digest_sha256 == first.digest_sha256.lower()


def test_duplicate_or_unknown_namespace_and_duplicate_role_are_rejected() -> None:
    all_namespaces = _complete_namespaces()
    with pytest.raises(ValueError, match="不可重複"):
        _source([*all_namespaces[:-1], all_namespaces[0]])
    with pytest.raises(TypeError, match="已知的"):
        ValidatedNamespaceEvidenceV1(
            namespace="unknown_namespace",  # type: ignore[arg-type]
            presence=SourceEvidencePresenceV1.EMPTY,
            files=(),
        )
    repeated_file = _file("revision/marker.json", "same")
    with pytest.raises(ValueError, match="role_id 不可重複"):
        ValidatedNamespaceEvidenceV1(
            namespace=SourceEvidenceNamespaceV1.MARKET_REVISION,
            presence=SourceEvidencePresenceV1.PRESENT,
            files=(repeated_file, repeated_file),
        )


@pytest.mark.parametrize(
    "role_id",
    (
        "",
        "/absolute/receipt.json",
        "C:/root/receipt.json",
        "run\\receipt.json",
        "run/../receipt.json",
        "run//receipt.json",
        "https://host/receipt.json",
        "run/receipt\n.json",
        "run/receipt\x01.json",
        "run／receipt.json",
        "run/%2e%2e/receipt.json",
    ),
)
def test_role_id_must_be_a_normalized_relative_identifier(role_id: str) -> None:
    with pytest.raises((TypeError, ValueError)):
        ValidatedEvidenceFileV1(role_id=role_id, sha256="a" * 64)


@pytest.mark.parametrize("bad_hash", ("", "A" * 64, "g" * 64, "sha256:" + "a" * 64))
def test_file_hash_requires_canonical_lowercase_sha256(bad_hash: str) -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        ValidatedEvidenceFileV1(role_id="revision/receipt.json", sha256=bad_hash)


def test_scope_cutoff_and_schema_are_validated() -> None:
    for invalid_scope in ("", "../db", "/db", "C:\\db", "db/name", " db"):
        with pytest.raises(ValueError, match="scope_id"):
            _source(scope_id=invalid_scope)
    with pytest.raises(TypeError, match="date"):
        _source(cutoff_date=datetime(2024, 1, 22, tzinfo=timezone.utc))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="schema_version"):
        _source(schema_version=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="不支援"):
        _source(schema_version="validated-source-evidence.v2")


def test_namespace_presence_must_match_file_collection() -> None:
    with pytest.raises(ValueError, match="不得包含"):
        ValidatedNamespaceEvidenceV1(
            namespace=SourceEvidenceNamespaceV1.MARKET_REVISION,
            presence=SourceEvidencePresenceV1.EMPTY,
            files=(_file("revision/marker.json", "marker"),),
        )
    with pytest.raises(ValueError, match="必須包含"):
        ValidatedNamespaceEvidenceV1(
            namespace=SourceEvidenceNamespaceV1.MARKET_REVISION,
            presence=SourceEvidencePresenceV1.PRESENT,
            files=(),
        )
