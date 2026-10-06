"""R026 四個 source revision namespace 的單次 aggregate contract。"""

from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
from pathlib import Path
from typing import Callable

import pytest

from data_module import (
    excluded_daily_price_revision,
    formal_market_revision,
    historical_session_revision,
    ml_daily_price_revision_gate,
)
from data_module.contracts.source_revision import (
    SOURCE_EVIDENCE_NAMESPACE_ORDER_V1,
    SOURCE_REVISION_EVIDENCE_SCHEMA_V1,
    SourceEvidenceNamespaceV1,
    SourceEvidencePresenceV1,
    ValidatedEvidenceFileV1,
    ValidatedNamespaceEvidenceV1,
)
from data_module.source_revision_evidence_collector import (
    collect_source_revision_evidence_v1,
)


def _namespace(
    namespace: SourceEvidenceNamespaceV1,
    *,
    presence: SourceEvidencePresenceV1 = SourceEvidencePresenceV1.EMPTY,
) -> ValidatedNamespaceEvidenceV1:
    files = (
        (ValidatedEvidenceFileV1("synthetic/receipt", "a" * 64),)
        if presence is SourceEvidencePresenceV1.PRESENT
        else ()
    )
    return ValidatedNamespaceEvidenceV1(
        namespace=namespace,
        presence=presence,
        files=files,
    )


def _install_collector_spies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    fail_at: int | None = None,
) -> list[tuple[object, ...]]:
    calls: list[tuple[object, ...]] = []
    collector_modules = (
        formal_market_revision,
        historical_session_revision,
        excluded_daily_price_revision,
        ml_daily_price_revision_gate,
    )
    collector_names = (
        "collect_market_revision_evidence",
        "collect_session_revision_evidence",
        "collect_excluded_daily_price_revision_evidence",
        "collect_daily_price_repair_receipt_evidence",
    )

    def make_spy(
        index: int,
        namespace: SourceEvidenceNamespaceV1,
        collector_name: str,
    ) -> Callable[..., ValidatedNamespaceEvidenceV1]:
        def spy(*args: object, **kwargs: object) -> ValidatedNamespaceEvidenceV1:
            calls.append((collector_name, *args, *kwargs.items()))
            if index == fail_at:
                raise RuntimeError(f"synthetic failure at collector {index}")
            return _namespace(namespace)

        return spy

    for index, (module, name, namespace) in enumerate(
        zip(
            collector_modules,
            collector_names,
            SOURCE_EVIDENCE_NAMESPACE_ORDER_V1,
            strict=True,
        )
    ):
        monkeypatch.setattr(module, name, make_spy(index, namespace, name))

    def legacy_gate_must_not_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("aggregate must not call the legacy composite gate")

    monkeypatch.setattr(
        ml_daily_price_revision_gate,
        "check_daily_price_source_revision",
        legacy_gate_must_not_run,
    )
    return calls


def test_aggregate_calls_each_typed_collector_once_in_fixed_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_collector_spies(monkeypatch)
    database_path = tmp_path / "sqlite" / "twstock.db"
    cutoff = date(2024, 1, 20)
    explicit_path = tmp_path / "receipt.json"

    result = collect_source_revision_evidence_v1(
        database_path=database_path,
        scope_id="synthetic-db-01",
        cutoff_date=cutoff,
        symbols=["2330"],
        explicit_path=explicit_path,
    )

    assert [call[0] for call in calls] == [
        "collect_market_revision_evidence",
        "collect_session_revision_evidence",
        "collect_excluded_daily_price_revision_evidence",
        "collect_daily_price_repair_receipt_evidence",
    ]
    assert len(calls) == 4
    assert result.schema_version == SOURCE_REVISION_EVIDENCE_SCHEMA_V1
    assert result.scope_id == "synthetic-db-01"
    assert result.cutoff_date is cutoff
    assert tuple(item.namespace for item in result.namespaces) == (
        SOURCE_EVIDENCE_NAMESPACE_ORDER_V1
    )
    assert all(item.presence is SourceEvidencePresenceV1.EMPTY for item in result.namespaces)
    assert calls[-1][0] == "collect_daily_price_repair_receipt_evidence"
    assert calls[-1][1:] == (
        ("database_path", database_path),
        ("decision_date", cutoff),
        ("symbols", ["2330"]),
        ("explicit_path", explicit_path),
    )


@pytest.mark.parametrize("fail_at", [0, 1, 2, 3])
def test_aggregate_propagates_each_collector_failure_without_partial_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fail_at: int,
) -> None:
    calls = _install_collector_spies(monkeypatch, fail_at=fail_at)

    with pytest.raises(RuntimeError, match=f"collector {fail_at}"):
        collect_source_revision_evidence_v1(
            database_path=tmp_path / "sqlite" / "twstock.db",
            scope_id="synthetic-db-01",
            cutoff_date=date(2024, 1, 20),
        )

    assert len(calls) == fail_at + 1


def test_aggregate_rejects_non_exact_cutoff_before_collectors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_collector_spies(monkeypatch)

    with pytest.raises(TypeError, match="cutoff_date"):
        collect_source_revision_evidence_v1(
            database_path=tmp_path / "sqlite" / "twstock.db",
            scope_id="synthetic-db-01",
            cutoff_date=datetime(2024, 1, 20),  # type: ignore[arg-type]
        )

    assert calls == []


def test_aggregate_uses_contract_to_reject_path_like_scope_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_collector_spies(monkeypatch)

    with pytest.raises(ValueError, match="scope_id"):
        collect_source_revision_evidence_v1(
            database_path=tmp_path / "sqlite" / "twstock.db",
            scope_id="C:/data/sqlite/twstock.db",
            cutoff_date=date(2024, 1, 20),
        )
    assert calls == []


def test_aggregate_digest_binds_caller_scope_and_cutoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_collector_spies(monkeypatch)
    database_path = tmp_path / "sqlite" / "twstock.db"

    base = collect_source_revision_evidence_v1(
        database_path=database_path,
        scope_id="source-logical-id-a",
        cutoff_date=date(2024, 1, 20),
    )
    same = collect_source_revision_evidence_v1(
        database_path=database_path,
        scope_id="source-logical-id-a",
        cutoff_date=date(2024, 1, 20),
    )
    different_scope = collect_source_revision_evidence_v1(
        database_path=database_path,
        scope_id="source-logical-id-b",
        cutoff_date=date(2024, 1, 20),
    )
    different_cutoff = collect_source_revision_evidence_v1(
        database_path=database_path,
        scope_id="source-logical-id-a",
        cutoff_date=date(2024, 1, 21),
    )

    assert base.digest_sha256 == same.digest_sha256
    assert base.digest_sha256 != different_scope.digest_sha256
    assert base.digest_sha256 != different_cutoff.digest_sha256


def test_real_collectors_build_one_isolated_mixed_presence_aggregate(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    database_path = data_root / "sqlite" / "twstock.db"
    database_path.parent.mkdir(parents=True)
    receipt_path = data_root / ml_daily_price_revision_gate.REPAIR_RECEIPT_RELATIVE_DIR / "receipt.json"
    receipt_path.parent.mkdir(parents=True)
    receipt_bytes = json.dumps(
        {
            "schema_version": ml_daily_price_revision_gate.REPAIR_SCHEMA,
            "receipt_kind": "historical_price_spike_repair",
            "status": "applied",
            "source_date": "2024-01-21",
            "allowlist_count": 1,
            "rows": [{"symbol": "2330", "date": "2024-01-21"}],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    receipt_path.write_bytes(receipt_bytes)

    result = collect_source_revision_evidence_v1(
        database_path=database_path,
        scope_id="synthetic-db-01",
        cutoff_date=date(2024, 1, 20),
    )

    assert tuple(item.namespace for item in result.namespaces) == (
        SOURCE_EVIDENCE_NAMESPACE_ORDER_V1
    )
    assert tuple(item.presence for item in result.namespaces) == (
        SourceEvidencePresenceV1.EMPTY,
        SourceEvidencePresenceV1.EMPTY,
        SourceEvidencePresenceV1.EMPTY,
        SourceEvidencePresenceV1.PRESENT,
    )
    direct = result.namespaces[-1]
    assert direct.files == (
        ValidatedEvidenceFileV1(
            role_id="automatic/b3V0cHV0L3NjaGVkdWxlZC9kYWlseV9wcmljZV9yZXBhaXJfcmVjZWlwdHMvMjAyNjA1MjAvaGlzdG9yaWNhbF9wcmljZV9zcGlrZV8yMDI2MDkyMS9yZWNlaXB0Lmpzb24",
            sha256=hashlib.sha256(receipt_bytes).hexdigest(),
        ),
    )
    assert len(result.digest_sha256) == 64
    assert result.digest_sha256 == collect_source_revision_evidence_v1(
        database_path=database_path,
        scope_id="synthetic-db-01",
        cutoff_date=date(2024, 1, 20),
    ).digest_sha256
