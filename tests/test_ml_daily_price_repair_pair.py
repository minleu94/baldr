from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from data_module import excluded_daily_price_revision
from data_module import formal_market_revision
from data_module import historical_session_revision
from data_module import ml_daily_price_revision_gate as gate
from data_module.contracts.source_revision import (
    SourceEvidenceNamespaceV1,
    SourceEvidencePresenceV1,
    ValidatedNamespaceEvidenceV1,
)


def _final_payload(database_path: Path, *, source_date: str = "2024-01-02") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": gate.REPAIR_SCHEMA,
        "receipt_kind": "historical_price_spike_repair",
        "status": "applied",
        "db_path": str(database_path.resolve()),
        "source_date": source_date,
        "allowlist_count": 1,
        "allowlist_hash": "sha256:" + "1" * 64,
        "plan_hash": "sha256:" + "2" * 64,
        "canonical_sha256": "sha256:" + "3" * 64,
        "source_update_columns": ["收盤價"],
        "rows": [
            {
                "date": source_date,
                "symbol": "2330",
                "before": {"收盤價": "100"},
                "after": {"收盤價": "101"},
                "source": {"receipt": "pinned"},
                "differing_fields": ["收盤價"],
            }
        ],
    }
    payload["receipt_sha256"] = "sha256:" + hashlib.sha256(
        (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    ).hexdigest()
    return payload


def _write_pair(
    tmp_path: Path,
    *,
    pending_status: str = "applied_receipt_written",
    pending_source_date: str = "2024-01-02",
    pending_count: object = 1,
    final_status: str = "applied",
    final_source_date: str = "2024-01-02",
) -> tuple[Path, Path, Path]:
    database_path = tmp_path / "data" / "sqlite" / "source.db"
    database_path.parent.mkdir(parents=True)
    database_path.write_bytes(b"read-only source identity")
    pair_root = tmp_path / "pair"
    pair_root.mkdir()
    final = _final_payload(database_path, source_date=final_source_date)
    final["status"] = final_status
    # The final receipt's actual-bytes logical hash is verified independently.
    final.pop("receipt_sha256")
    final["receipt_sha256"] = "sha256:" + hashlib.sha256(
        (json.dumps(final, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    ).hexdigest()
    pending = {
        "schema_version": gate.REPAIR_SCHEMA,
        "receipt_kind": "historical_price_spike_repair_pending",
        "status": pending_status,
        "db_path": str(database_path.resolve()),
        "source_date": pending_source_date,
        "allowlist_count": pending_count,
        "allowlist_hash": final["allowlist_hash"],
        "plan_hash": final["plan_hash"],
        "canonical_sha256": final["canonical_sha256"],
    }
    (pair_root / "pending.json").write_text(
        json.dumps(pending, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    (pair_root / "receipt.json").write_text(
        json.dumps(final, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    return database_path, pair_root, pair_root / "pending.json"


def _inspect_research_pair(database_path: Path, pair_root: Path):
    return gate._inspect_daily_price_repair_receipts_once(
        database_path=database_path,
        decision=gate.date(2024, 2, 15),
        symbols=frozenset({"2330"}),
        explicit_path=pair_root,
        strict_explicit_slots=True,
        allow_source_revision_research=True,
    )


def test_research_accepts_only_completed_sibling_pair_and_keeps_both_physical_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path, pair_root, pending_path = _write_pair(tmp_path)

    summary, evidence = _inspect_research_pair(database_path, pair_root)

    assert summary is not None
    assert summary["checked_receipt_count"] == 2
    assert len(summary["checked_receipts"]) == 1
    pair_summary = summary["checked_receipts"][0]["completed_pending_pair"]
    assert pair_summary["affected_row_count"] == 1
    assert summary["relevant_row_count"] == 1
    assert {item.role_id for item in evidence} == {
        "explicit/" + hashlib.sha256(path.resolve().as_posix().encode("utf-8")).hexdigest()
        for path in (pending_path, pair_root / "receipt.json")
    }
    assert {item.sha256 for item in evidence} == {
        hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (pending_path, pair_root / "receipt.json")
    }

    empty_namespaces = {
        namespace: ValidatedNamespaceEvidenceV1(
            namespace=namespace,
            presence=SourceEvidencePresenceV1.EMPTY,
            files=(),
        )
        for namespace in SourceEvidenceNamespaceV1
    }
    monkeypatch.setattr(
        formal_market_revision,
        "inspect_market_revision_state",
        lambda _path: SimpleNamespace(
            evidence=empty_namespaces[SourceEvidenceNamespaceV1.MARKET_REVISION],
            runs=(),
        ),
    )
    monkeypatch.setattr(
        gate,
        "_inspect_session_revision_state",
        lambda _path: (
            empty_namespaces[SourceEvidenceNamespaceV1.HISTORICAL_SESSION_REVISION],
            [],
        ),
    )
    monkeypatch.setattr(
        excluded_daily_price_revision,
        "collect_excluded_revision_capture",
        lambda _path: excluded_daily_price_revision.ExcludedRevisionCaptureV1(
            evidence=empty_namespaces[
                SourceEvidenceNamespaceV1.EXCLUDED_DAILY_PRICE_REVISION
            ],
            dependencies=(),
            runs=(),
        ),
    )
    integrated = gate.check_daily_price_source_revision(
        database_path=database_path,
        decision_date="2024-02-15",
        symbols=("2330",),
        explicit_path=pair_root,
        allow_source_revision_research=True,
    )
    assert integrated is not None
    assert integrated["checked_receipt_count"] == 2
    daily_evidence = next(
        item
        for item in integrated["source_revision_evidence"]["namespaces"]
        if item["namespace"]
        == SourceEvidenceNamespaceV1.DAILY_PRICE_REPAIR_RECEIPT.value
    )
    assert len(daily_evidence["files"]) == 2
    assert {
        item["sha256"] for item in daily_evidence["files"]
    } == {
        hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (pending_path, pair_root / "receipt.json")
    }

    with pytest.raises(gate.DailyPriceSourceRevisionError, match="pending"):
        gate._check_receipt_with_evidence(
            path=pending_path,
            decision=gate.date(2024, 2, 15),
            symbols=frozenset({"2330"}),
            allow_source_revision_research=False,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("pending_status", "pending", "unresolved"),
        ("pending_status", "commit_receipt_write_failed", "unresolved"),
        ("final_status", "rolled_back", "not applied"),
        ("pending_source_date", "2024-01-03", "source_date mismatch"),
        ("pending_count", True, "allowlist_count must be an integer"),
    ],
)
def test_research_rejects_incomplete_or_mismatched_pairs(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    kwargs = {
        "pending_status": "applied_receipt_written",
        "pending_source_date": "2024-01-02",
        "pending_count": 1,
        "final_status": "applied",
        "final_source_date": "2024-01-02",
    }
    kwargs[field] = value
    database_path, pair_root, _pending_path = _write_pair(tmp_path, **kwargs)

    with pytest.raises(gate.DailyPriceSourceRevisionError, match=message):
        _inspect_research_pair(database_path, pair_root)


def test_research_rejects_missing_final_sibling(tmp_path: Path) -> None:
    database_path, pair_root, _pending_path = _write_pair(tmp_path)
    (pair_root / "receipt.json").unlink()

    with pytest.raises(gate.DailyPriceSourceRevisionError, match="final receipt is missing"):
        _inspect_research_pair(database_path, pair_root)
