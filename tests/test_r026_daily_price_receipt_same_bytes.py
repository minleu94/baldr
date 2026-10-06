"""R026 direct repair receipt 的同 bytes parse/hash characterization。"""

from __future__ import annotations

import hashlib
import json
import os
import base64
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from data_module import excluded_daily_price_revision, formal_market_revision
from data_module import historical_session_revision
from data_module import ml_daily_price_revision_gate as gate
from data_module.contracts.source_revision import (
    SourceEvidenceNamespaceV1,
    SourceEvidencePresenceV1,
)


def _receipt_bytes(source_date: str) -> bytes:
    payload = {
        "schema_version": gate.REPAIR_SCHEMA,
        "receipt_kind": "historical_price_spike_repair",
        "status": "applied",
        "source_date": source_date,
        "allowlist_count": 1,
        "rows": [{"symbol": "2330", "date": source_date}],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _isolate_other_revision_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    def allow(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(formal_market_revision, "assert_market_revision_safe", allow)
    monkeypatch.setattr(historical_session_revision, "assert_session_revision_safe", allow)
    monkeypatch.setattr(
        excluded_daily_price_revision,
        "assert_excluded_source_revision_safe",
        allow,
    )


def _check(*, database_path: Path, receipt_path: Path) -> dict[str, object]:
    result = gate.check_daily_price_source_revision(
        database_path=database_path,
        decision_date="2024-01-20",
        symbols=["2330"],
        explicit_path=receipt_path,
    )
    assert result is not None
    summaries = result["checked_receipts"]
    assert isinstance(summaries, list) and len(summaries) == 1
    summary = summaries[0]
    assert isinstance(summary, dict)
    return summary


def test_receipt_summary_hash_uses_the_bytes_read_for_json_parse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_other_revision_guards(monkeypatch)
    database_path = tmp_path / "data" / "sqlite" / "twstock.db"
    database_path.parent.mkdir(parents=True)
    receipt_path = tmp_path / "receipt.json"
    original_bytes = _receipt_bytes("2024-01-21")
    replacement_bytes = _receipt_bytes("2024-01-22")
    original_text = original_bytes.decode("utf-8")
    receipt_path.write_bytes(original_bytes)

    original_loads: Any = gate.json.loads
    replaced = False

    def parse_then_atomically_replace(
        value: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        nonlocal replaced
        parsed = original_loads(value, *args, **kwargs)
        if value == original_text and not replaced:
            replacement_path = receipt_path.with_name("receipt.replacement")
            replacement_path.write_bytes(replacement_bytes)
            os.replace(replacement_path, receipt_path)
            replaced = True
        return parsed

    monkeypatch.setattr(gate.json, "loads", parse_then_atomically_replace)

    summary = _check(database_path=database_path, receipt_path=receipt_path)

    assert replaced is True
    assert receipt_path.read_bytes() == replacement_bytes
    assert summary["source_date"] == "2024-01-21"
    assert summary["receipt_hash"] == "sha256:" + hashlib.sha256(original_bytes).hexdigest()


def test_direct_receipt_keeps_legacy_summary_fields_and_hash_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_other_revision_guards(monkeypatch)
    database_path = tmp_path / "data" / "sqlite" / "twstock.db"
    database_path.parent.mkdir(parents=True)
    receipt_path = tmp_path / "receipt.json"
    receipt_bytes = _receipt_bytes("2024-01-21")
    receipt_path.write_bytes(receipt_bytes)

    summary = _check(database_path=database_path, receipt_path=receipt_path)

    assert set(summary) == {
        "schema_version",
        "receipt_path",
        "receipt_hash",
        "receipt_kind",
        "status",
        "source_date",
        "known_at",
        "known_after_decision",
        "affected_row_count",
        "scope_mode",
        "relevant_row_count",
        "relevant_dates",
        "relevant_symbols",
        "policy",
    }
    assert summary["receipt_path"] == str(receipt_path.resolve())
    assert summary["receipt_hash"] == "sha256:" + hashlib.sha256(receipt_bytes).hexdigest()
    assert summary["source_date"] == "2024-01-21"


def test_typed_receipt_evidence_uses_same_bytes_and_explicit_role_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_other_revision_guards(monkeypatch)
    database_path = tmp_path / "data" / "sqlite" / "twstock.db"
    database_path.parent.mkdir(parents=True)
    receipt_path = tmp_path / "receipt.json"
    receipt_bytes = _receipt_bytes("2024-01-21")
    receipt_path.write_bytes(receipt_bytes)

    original_read_bytes = Path.read_bytes
    read_paths: list[Path] = []

    def count_reads(path: Path) -> bytes:
        if path.resolve() == receipt_path.resolve():
            read_paths.append(path.resolve())
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", count_reads)
    namespace = gate.collect_daily_price_repair_receipt_evidence(
        database_path=database_path,
        decision_date="2024-01-20",
        symbols=["2330"],
        explicit_path=receipt_path,
    )

    assert namespace.namespace is SourceEvidenceNamespaceV1.DAILY_PRICE_REPAIR_RECEIPT
    assert namespace.presence is SourceEvidencePresenceV1.PRESENT
    assert len(namespace.files) == 1
    assert read_paths == [receipt_path.resolve()]
    evidence = namespace.files[0]
    expected_role = "explicit/" + hashlib.sha256(
        receipt_path.resolve().as_posix().encode("utf-8")
    ).hexdigest()
    assert evidence.role_id == expected_role
    assert evidence.sha256 == hashlib.sha256(receipt_bytes).hexdigest()


def test_public_gate_and_typed_collector_share_one_receipt_bytes_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_other_revision_guards(monkeypatch)
    database_path = tmp_path / "data" / "sqlite" / "twstock.db"
    database_path.parent.mkdir(parents=True)
    receipt_path = tmp_path / "receipt.json"
    original_bytes = _receipt_bytes("2024-01-21")
    replacement_bytes = _receipt_bytes("2024-01-22")
    original_text = original_bytes.decode("utf-8")
    receipt_path.write_bytes(original_bytes)

    original_loads: Any = gate.json.loads
    replaced = False

    def replace_after_parse(value: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal replaced
        parsed = original_loads(value, *args, **kwargs)
        if value == original_text and not replaced:
            replacement_path = receipt_path.with_name("receipt.replacement")
            replacement_path.write_bytes(replacement_bytes)
            os.replace(replacement_path, receipt_path)
            replaced = True
        return parsed

    monkeypatch.setattr(gate.json, "loads", replace_after_parse)
    summary, evidence_files = gate._inspect_daily_price_repair_receipts_once(
        database_path=database_path,
        decision=date(2024, 1, 20),
        symbols=frozenset({"2330"}),
        explicit_path=receipt_path,
        strict_explicit_slots=False,
    )

    assert replaced is True
    assert receipt_path.read_bytes() == replacement_bytes
    assert summary is not None
    assert summary["checked_receipts"][0]["source_date"] == "2024-01-21"
    expected_hash = hashlib.sha256(original_bytes).hexdigest()
    assert summary["checked_receipts"][0]["receipt_hash"] == f"sha256:{expected_hash}"
    assert len(evidence_files) == 1
    assert evidence_files[0].sha256 == expected_hash


def test_typed_automatic_receipt_uses_relative_role_and_deduplicates_explicit_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_other_revision_guards(monkeypatch)
    data_root = tmp_path / "data"
    database_path = data_root / "sqlite" / "twstock.db"
    database_path.parent.mkdir(parents=True)
    receipt_path = data_root / gate.REPAIR_RECEIPT_RELATIVE_DIR / "receipt.json"
    receipt_path.parent.mkdir(parents=True)
    receipt_bytes = _receipt_bytes("2024-01-21")
    receipt_path.write_bytes(receipt_bytes)

    namespace = gate.collect_daily_price_repair_receipt_evidence(
        database_path=database_path,
        decision_date="2024-01-20",
        symbols=["2330"],
        explicit_path=receipt_path,
    )

    relative = receipt_path.resolve().relative_to(data_root.resolve()).as_posix()
    role_token = base64.urlsafe_b64encode(relative.encode("utf-8")).decode("ascii").rstrip("=")
    assert namespace.presence is SourceEvidencePresenceV1.PRESENT
    assert len(namespace.files) == 1
    assert namespace.files[0].role_id == f"automatic/{role_token}"
    assert namespace.files[0].sha256 == hashlib.sha256(receipt_bytes).hexdigest()


def test_typed_receipt_enforces_cutoff_and_does_not_return_partial_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_other_revision_guards(monkeypatch)
    data_root = tmp_path / "data"
    database_path = data_root / "sqlite" / "twstock.db"
    database_path.parent.mkdir(parents=True)
    auto_path = data_root / gate.REPAIR_RECEIPT_RELATIVE_DIR / "receipt.json"
    auto_path.parent.mkdir(parents=True)
    auto_path.write_bytes(_receipt_bytes("2024-01-21"))

    before_cutoff = gate.collect_daily_price_repair_receipt_evidence(
        database_path=database_path,
        decision_date="2024-01-20",
        symbols=["2330"],
    )
    assert before_cutoff.presence is SourceEvidencePresenceV1.PRESENT
    with pytest.raises(gate.DailyPriceSourceRevisionError, match="blocks this PIT prefix"):
        gate.collect_daily_price_repair_receipt_evidence(
            database_path=database_path,
            decision_date="2024-01-21",
            symbols=["2330"],
        )

    malformed_explicit = tmp_path / "malformed.json"
    malformed_explicit.write_bytes(b"{invalid json")
    with pytest.raises(gate.DailyPriceSourceRevisionError, match="receipt is unreadable"):
        gate.collect_daily_price_repair_receipt_evidence(
            database_path=database_path,
            decision_date="2024-01-20",
            symbols=["2330"],
            explicit_path=malformed_explicit,
        )


def test_typed_pending_receipt_is_present_and_blocks_at_its_source_date(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_other_revision_guards(monkeypatch)
    database_path = tmp_path / "data" / "sqlite" / "twstock.db"
    database_path.parent.mkdir(parents=True)
    pending_path = tmp_path / "pending.json"
    pending_path.write_text(
        json.dumps(
            {
                "schema_version": gate.REPAIR_SCHEMA,
                "receipt_kind": "historical_price_spike_repair_pending",
                "status": "pending",
                "source_date": "2024-01-21",
                "allowlist_count": 1,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    before_source_date = gate.collect_daily_price_repair_receipt_evidence(
        database_path=database_path,
        decision_date="2024-01-20",
        symbols=["2330"],
        explicit_path=pending_path,
    )
    assert before_source_date.presence is SourceEvidencePresenceV1.PRESENT
    assert len(before_source_date.files) == 1

    with pytest.raises(gate.DailyPriceSourceRevisionError, match="blocks this PIT prefix"):
        gate.collect_daily_price_repair_receipt_evidence(
            database_path=database_path,
            decision_date="2024-01-21",
            symbols=["2330"],
            explicit_path=pending_path,
        )


def test_invalid_direct_receipt_keeps_legacy_fail_closed_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_other_revision_guards(monkeypatch)
    database_path = tmp_path / "data" / "sqlite" / "twstock.db"
    database_path.parent.mkdir(parents=True)
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_bytes(b"{invalid json")

    with pytest.raises(gate.DailyPriceSourceRevisionError, match="receipt is unreadable"):
        gate.check_daily_price_source_revision(
            database_path=database_path,
            decision_date="2024-01-20",
            symbols=["2330"],
            explicit_path=receipt_path,
        )


def test_absent_direct_receipt_keeps_legacy_none_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_other_revision_guards(monkeypatch)
    database_path = tmp_path / "data" / "sqlite" / "twstock.db"
    database_path.parent.mkdir(parents=True)

    assert gate.check_daily_price_source_revision(
        database_path=database_path,
        decision_date="2024-01-20",
        symbols=["2330"],
    ) is None


def test_typed_receipt_namespace_reports_empty_without_changing_legacy_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_other_revision_guards(monkeypatch)
    database_path = tmp_path / "data" / "sqlite" / "twstock.db"
    database_path.parent.mkdir(parents=True)

    assert gate.check_daily_price_source_revision(
        database_path=database_path,
        decision_date="2024-01-20",
        symbols=["2330"],
    ) is None

    namespace = gate.collect_daily_price_repair_receipt_evidence(
        database_path=database_path,
        decision_date="2024-01-20",
        symbols=["2330"],
    )
    assert namespace.namespace is SourceEvidenceNamespaceV1.DAILY_PRICE_REPAIR_RECEIPT
    assert namespace.presence is SourceEvidencePresenceV1.EMPTY
    assert namespace.files == ()


def test_typed_explicit_directory_rejects_malformed_slot_but_legacy_keeps_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_other_revision_guards(monkeypatch)
    database_path = tmp_path / "data" / "sqlite" / "twstock.db"
    database_path.parent.mkdir(parents=True)
    explicit_directory = tmp_path / "explicit-receipts"
    explicit_directory.mkdir()
    (explicit_directory / "receipt.json").mkdir()

    assert gate.check_daily_price_source_revision(
        database_path=database_path,
        decision_date="2024-01-20",
        symbols=["2330"],
        explicit_path=explicit_directory,
    ) is None

    with pytest.raises(gate.DailyPriceSourceRevisionError, match="explicit receipt slot"):
        gate.collect_daily_price_repair_receipt_evidence(
            database_path=database_path,
            decision_date="2024-01-20",
            symbols=["2330"],
            explicit_path=explicit_directory,
        )
