from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app_module.forward_source_observation import (
    ForwardSourceObservationError,
    ForwardSourceObservationRecorder,
    verify_forward_source_observation_readback,
)
from data_module.daily_price_qualification_binding import (
    DAILY_PRICE_QUALIFICATION_BINDING_SCHEMA_V1,
    DailyPriceQualificationError,
    DailyPriceRevisionLedger,
    DailyPriceRowRevision,
    PinnedDailyPriceQualificationResolver,
    _canonical_bytes,
    evaluate_bound_daily_price_row_qualification,
    verify_qualified_binding_payload,
)

_TAIPEI = ZoneInfo("Asia/Taipei")


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _decision(source_id: str = "twse.mi_index.daily_price") -> dict[str, object]:
    return {
        "source_id": source_id,
        "decision_revision_id": "accept-daily-price-20261022",
        "parent_revision_id": None,
        "status": "accepted",
        "allowed_use_cases": ["forward_outcome_evaluation"],
        "blockers": [],
        "license_evidence_ids": ["sha256:" + "a" * 64],
        "quality_evidence_ids": ["sha256:" + "b" * 64],
        "pit_evidence_ids": ["sha256:" + "c" * 64],
        "owner_role": "quant_data_architect",
        "reviewer_role": "operations_owner",
        "decided_at": "2026-10-22T00:00:00+00:00",
        "rollback_reference": "initial_decision",
    }


def _resolver(tmp_path: Path, source_id: str = "twse.mi_index.daily_price"):
    payload = {
        "schema_version": DAILY_PRICE_QUALIFICATION_BINDING_SCHEMA_V1,
        "binding_id": "daily-price-qualification-test-v1",
        "created_at": "2026-10-22T00:00:00+00:00",
        "decision": _decision(source_id),
    }
    raw = _canonical_bytes(payload) + b"\n"
    path = tmp_path / "qualification-binding.json"
    path.write_bytes(raw)
    return PinnedDailyPriceQualificationResolver(path, _sha(raw))


def _qualified_binding(tmp_path: Path):
    resolver = _resolver(tmp_path)
    policy = resolver.build_policy(
        temporal_role="outcome_realization",
        cutoff_at=datetime(2026, 10, 22, 16, 0, tzinfo=_TAIPEI),
        event_price_date=date(2026, 10, 20),
        outcome_price_date=date(2026, 10, 20),
    )
    revision = DailyPriceRowRevision(
        source_id="twse.mi_index.daily_price",
        source_date="20261020",
        trading_date=date(2026, 10, 20),
        stock_code="2330",
        revision_number=1,
        revision_id="twse.mi_index.daily_price:20261020:2330:r1:1234567890abcdef",
        publication_sha256="sha256:" + "1" * 64,
        sqlite_projection_row_sha256="sha256:" + "2" * 64,
        first_observed_at="2026-10-20T06:15:00+00:00",
        written_at="2026-10-20T06:16:00+00:00",
        available_at="2026-10-20T07:00:00+00:00",
        availability_basis="daily-hour.v1",
    )

    class CompleteLedger:
        revision_closure_verified = True

        def resolve_row_revision(self, **_kwargs):
            return revision

    ledger = CompleteLedger()
    bound = {
        "status": "source_identity_bound",
        "reason_code": "ok",
        "source_id": "twse.mi_index.daily_price",
        "source_date": "20261020",
        "stock_code": "2330",
        "publication_sha256": revision.publication_sha256,
        "sqlite_projection_row_sha256": revision.sqlite_projection_row_sha256,
    }
    qualified = evaluate_bound_daily_price_row_qualification(
        bound_row=bound,
        revision_ledger=ledger,  # type: ignore[arg-type]
        policy=policy,
    )
    return resolver, policy, ledger, qualified


def test_accepted_source_decision_cannot_cross_bind_another_market(tmp_path: Path):
    resolver = _resolver(tmp_path, "twse.mi_index.daily_price")
    policy = resolver.build_policy(
        temporal_role="outcome_realization",
        cutoff_at=datetime(2026, 10, 22, 16, 0, tzinfo=_TAIPEI),
    )

    class CompleteLedger:
        revision_closure_verified = True

        def resolve_row_revision(self, **_kwargs):
            raise AssertionError("source mismatch must fail before ledger lookup")

    result = evaluate_bound_daily_price_row_qualification(
        bound_row={
            "status": "source_identity_bound",
            "source_id": "tpex.daily_close_quotes",
            "source_date": "20261020",
            "stock_code": "2330",
            "publication_sha256": "sha256:" + "1" * 64,
            "sqlite_projection_row_sha256": "sha256:" + "2" * 64,
        },
        revision_ledger=CompleteLedger(),  # type: ignore[arg-type]
        policy=policy,
    )
    assert result["status"] == "unknown"
    assert result["reason_code"] == "acceptance_source_id_mismatch"
    assert result["source_use_accepted"] is False
    assert result["pit_eligible"] is False


def test_qualification_proof_requires_trusted_resolver_and_complete_ledger(tmp_path: Path):
    resolver, policy, ledger, binding = _qualified_binding(tmp_path)
    assert binding["status"] == "source_qualified"
    assert verify_qualified_binding_payload(binding) is False
    assert verify_qualified_binding_payload(
        binding, resolver=resolver, policy=policy, revision_ledger=ledger  # type: ignore[arg-type]
    ) is True

    forged = dict(binding)
    forged["available_at"] = "2026-10-20T06:00:00+00:00"
    body = {key: value for key, value in forged.items() if key != "qualification_proof_sha256"}
    forged["qualification_proof_sha256"] = _sha(_canonical_bytes(body))
    assert verify_qualified_binding_payload(
        forged, resolver=resolver, policy=policy, revision_ledger=ledger  # type: ignore[arg-type]
    ) is False

    baseline_policy = resolver.build_policy(
        temporal_role="decision_baseline",
        cutoff_at=datetime(2026, 10, 22, 16, 0, tzinfo=_TAIPEI),
    )
    assert verify_qualified_binding_payload(
        binding,
        resolver=resolver,
        policy=baseline_policy,
        revision_ledger=ledger,  # type: ignore[arg-type]
    ) is False


def test_unverified_revision_closure_cannot_qualify_or_resolve(tmp_path: Path):
    ledger = DailyPriceRevisionLedger(output_root=tmp_path, data_root=tmp_path)
    assert ledger.revision_closure_verified is False
    with pytest.raises(DailyPriceQualificationError, match="revision_closure_unverified"):
        ledger.resolve_row_revision(
            source_id="twse.mi_index.daily_price",
            source_date="20261020",
            stock_code="2330",
            publication_sha256="sha256:" + "1" * 64,
            sqlite_projection_row_sha256="sha256:" + "2" * 64,
            cutoff_at=datetime(2026, 10, 22, 16, 0, tzinfo=_TAIPEI),
        )


def test_ledger_rejects_publication_projection_row_drift(tmp_path: Path, monkeypatch):
    import data_module.twse_daily_price_publication as twse

    projection_sha = "sha256:" + "a" * 64
    expected_row_sha = "sha256:" + "b" * 64
    raw_sha = "sha256:" + "c" * 64
    custody_sha = "sha256:" + "d" * 64
    observation_sha = "sha256:" + "e" * 64
    csv_sha = "sha256:" + "f" * 64
    projection_rel = "scheduled/twse_daily_price_projection/20261020/projection.json"

    def load_projection_manifest(**_kwargs):
        return {
            "source_id": "twse.mi_index.daily_price",
            "parser_id": "twse.mi_index.daily_price.v1",
            "first_observed_at": "2026-10-20T14:15:00+08:00",
            "observed_at": "2026-10-20T14:16:00+08:00",
            "raw_response_sha256": raw_sha,
            "custody_receipt_sha256": custody_sha,
            "observation_receipt_sha256": observation_sha,
            "csv_sha256": csv_sha,
            "observed_response_rows": [{
                "source_date": "20261020",
                "stock_code": "2330",
                "projection_row_sha256": expected_row_sha,
            }],
        }

    monkeypatch.setattr(twse, "_load_projection_manifest", load_projection_manifest)
    output_root = tmp_path / "output"
    data_root = tmp_path / "data"
    output_root.mkdir()
    data_root.mkdir()
    publication_path = output_root / "publication.json"
    body = {
        "schema_version": "twse-daily-price-sqlite-publication.v1",
        "source_id": "twse.mi_index.daily_price",
        "source_published_at": None,
        "written_at": "2026-10-20T06:17:00+00:00",
        "database_relative_path": "sqlite/twstock.db",
        "projection_manifests": [{"relative_path": projection_rel, "sha256": projection_sha}],
        "coverage_basis": "keys_observed_in_this_twse_response_only",
        "rows": [{
            "source_date": "20261020",
            "stock_code": "2330",
            "parser_id": "twse.mi_index.daily_price.v1",
            "first_observed_at": "2026-10-20T14:15:00+08:00",
            "written_at": "2026-10-20T14:17:00+08:00",
            "projection_manifest_relative_path": projection_rel,
            "projection_manifest_sha256": projection_sha,
            "raw_response_sha256": raw_sha,
            "custody_receipt_sha256": custody_sha,
            "observation_receipt_sha256": observation_sha,
            "csv_sha256": csv_sha,
            "projection_row_sha256": "sha256:" + "9" * 64,
            "sqlite_projection_row_sha256": "sha256:" + "8" * 64,
        }],
    }
    raw = _canonical_bytes({
        **body,
        "content_sha256": _sha(_canonical_bytes(body)),
    }) + b"\n"
    publication_path.write_bytes(raw)
    ledger = DailyPriceRevisionLedger(output_root=output_root, data_root=data_root)
    with pytest.raises(DailyPriceQualificationError, match="projection_hash_drift"):
        ledger.register_publication(
            source_id="twse.mi_index.daily_price",
            relative_path="publication.json",
        )


def _reference(*, run_id: str, manifest_path: str, manifest_sha256: str):
    return {
        "schema_version": "forward-source-observations.v1",
        "run_id": run_id,
        "manifest_path": manifest_path,
        "manifest_sha256": manifest_sha256,
        "query_count": 0,
        "row_count": 0,
        "chunk_count": 0,
        "source_availability": "unknown",
        "pit_qualified": False,
        "training_eligible": False,
        "cross_read_snapshot_consistency": "not_guaranteed",
    }


def test_observation_reader_rejects_manifest_path_escape(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.json"
    raw = b"{}"
    outside.write_bytes(raw)
    reference = _reference(
        run_id="20261022T120000123456Z",
        manifest_path="../outside.json",
        manifest_sha256=_sha(raw),
    )
    with pytest.raises(ForwardSourceObservationError, match="reference_invalid"):
        verify_forward_source_observation_readback(output_root=root, reference=reference)


def test_observation_recorder_rejects_self_hashed_qualification_without_trust(tmp_path: Path):
    root = tmp_path.resolve()

    def write(path: Path, text: str) -> None:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)

    recorder = ForwardSourceObservationRecorder(
        run_id="20261022T120000123456Z",
        output_root=root,
        db_path=root / "market.sqlite3",
        writer=write,
    )
    recorder.begin_outcome(event_id="event-1", window_days=5)
    forged = {
        "status": "source_qualified",
        "source_id": "twse.mi_index.daily_price",
        "source_use_accepted": True,
        "pit_eligible": True,
        "training_eligible": True,
        "source_published_at": None,
        "available_at": "2026-10-20T07:00:00+00:00",
        "cutoff_at": "2026-10-22T16:00:00+00:00",
        "temporal_role": "outcome_realization",
        "acceptance_decision_id": "made-up",
        "acceptance_source_id": "twse.mi_index.daily_price",
        "acceptance_binding_sha256": "sha256:" + "a" * 64,
    }
    forged["qualification_proof_sha256"] = _sha(_canonical_bytes(forged))
    with pytest.raises(ForwardSourceObservationError, match="qualification_invalid"):
        recorder.observe_query(
            table="daily_prices",
            query="SELECT 日期 FROM daily_prices",
            parameters=(),
            rows=[("20261020",)],
            symbol="2330",
            purpose="daily_price_series",
            columns=("日期",),
            source_bindings=[forged],
        )
