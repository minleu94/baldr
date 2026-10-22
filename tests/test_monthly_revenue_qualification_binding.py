from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os

import pytest

from data_module.monthly_revenue_qualification_binding import (
    MONTHLY_REVENUE_QUALIFICATION_BINDING_SCHEMA_V2,
    MONTHLY_REVENUE_QUALIFICATION_DOCUMENT_SCHEMA_V1,
    MonthlyRevenueQualificationBindingError,
    PinnedMonthlyRevenueQualificationResolver,
)
from app_module.monthly_revenue_research_service import MonthlyRevenueResearchService
from data_module.monthly_revenue_revision_archive import (
    append_monthly_revenue_batch,
    raw_batch_from_openapi,
    read_monthly_revenue_revision_archive,
)
from data_module.monthly_revenue_use_policy import (
    MonthlyRevenueUse,
    evaluate_monthly_revenue_use,
)
from data_module.opendata_monthly_revenue import (
    OPENAPI_MONTHLY_REVENUE_ENDPOINTS,
    OPENAPI_MONTHLY_REVENUE_SOURCE_IDS,
    OpenApiMonthlyRevenueCapture,
    OpenApiMonthlyRevenueUnitProof,
    build_openapi_unit_field_map_bytes,
    prepare_openapi_monthly_revenue_batch,
    write_openapi_unit_proof_artifact_create_only,
)
from data_module.source_acceptance_decision_registry import (
    SourceAcceptanceDecisionRevision,
)
import data_module.monthly_revenue_qualification_binding as qualification_binding
import data_module.monthly_revenue_revision_archive as revision_archive


_CAPTURED_AT = datetime(2026, 10, 21, 7, 15, tzinfo=timezone.utc)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _batch(*, market: str = "twse", amount: str = "1.250", unit_proof=None):
    row = {
        "資料年月": "11509",
        "公司代號": "2330",
        "公司名稱": "隔離測試公司",
        "營業收入-當月營收": amount,
        "營業收入-上月營收": "10",
        "營業收入-去年當月營收": "8",
        "營業收入-上月比較增減(%)": "2.5",
        "營業收入-去年同月增減(%)": "3.5",
        "累計營業收入-當月累計營收": "20",
        "累計營業收入-去年累計營收": "16",
        "累計營業收入-前期比較增減(%)": "4.5",
        "出表日期": "1151010",
        "備註": "隔離測試",
        "產業別": "測試業",
    }
    raw = json.dumps([row], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    endpoint = OPENAPI_MONTHLY_REVENUE_ENDPOINTS[market]
    capture = OpenApiMonthlyRevenueCapture(
        market=market,
        requested_url=endpoint,
        response_url=endpoint,
        response_status=200,
        content_type_original_text="application/json; charset=utf-8",
        content_encoding_original_text="identity",
        content_length_original_text=str(len(raw)),
        response_body_complete=True,
        eof_observed=True,
        received_body_bytes=len(raw),
        body_observation_ended_at=_CAPTURED_AT,
        body_completed_at=_CAPTURED_AT,
        raw_response_bytes=raw,
    )
    return prepare_openapi_monthly_revenue_batch(
        capture=capture,
        successful_batch_completed_at=_CAPTURED_AT,
        unit_proof=unit_proof,
        trusted_unit_proof_sha256=(unit_proof.proof_sha256 if unit_proof else None),
    )


def _unit_proof(market: str) -> OpenApiMonthlyRevenueUnitProof:
    document = b"isolated official unit document fixture"
    document_sha = hashlib.sha256(document).hexdigest()
    endpoint = OPENAPI_MONTHLY_REVENUE_ENDPOINTS[market]
    field_map = build_openapi_unit_field_map_bytes(
        market=market,
        official_document_url="https://data.gov.tw/dataset/isolated-fixture",
        official_document_sha256=document_sha,
    )
    return OpenApiMonthlyRevenueUnitProof(
        market=market,
        source_id=OPENAPI_MONTHLY_REVENUE_SOURCE_IDS[market],
        endpoint_url=endpoint,
        official_document_url="https://data.gov.tw/dataset/isolated-fixture",
        official_document_bytes=document,
        official_document_sha256=document_sha,
        field_map_bytes=field_map,
        field_map_sha256=hashlib.sha256(field_map).hexdigest(),
        trusted_evidence_scope_id="isolated-test-anchor",
        source_unit_original_text="仟元",
        conversion_to_twd=Decimal("1000"),
    )


def _write_json(path, value: object) -> bytes:
    payload = _canonical_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return payload


def _binding_fixture(
    root,
    *,
    batch=None,
    decision_status: str = "limited",
    decided_at: str = "2026-10-21T08:30:00+00:00",
    with_unit_proof: bool = False,
):
    selected_batch = batch or _batch(
        unit_proof=_unit_proof("twse") if with_unit_proof else None
    )
    capture = selected_batch.capture
    source_id = capture.source_id
    decision = SourceAcceptanceDecisionRevision(
        source_id=source_id,
        decision_revision_id="decision:monthly-revenue:isolated-r1",
        parent_revision_id=None,
        status=decision_status,
        allowed_use_cases=("research_shadow",) if decision_status == "limited" else (),
        blockers=() if decision_status == "limited" else ("owner_review_pending",),
        license_evidence_ids=("license:source-scope:r1",),
        quality_evidence_ids=("quality:batch:r1",),
        pit_evidence_ids=("pit:limitation:r1",),
        owner_role="isolated_fixture_owner",
        reviewer_role="isolated_fixture_reviewer",
        decided_at=decided_at,
        rollback_reference="decision:monthly-revenue:isolated-r2",
    )
    documents = []
    common = {
        "schema_version": MONTHLY_REVENUE_QUALIFICATION_DOCUMENT_SCHEMA_V1,
        "source_id": source_id,
        "market": capture.market,
        "endpoint_url": capture.requested_url,
        "batch_sha256": capture.raw_response_sha256,
        "captured_at": qualification_binding._datetime_text(capture.body_completed_at),
        "available_at": qualification_binding._datetime_text(selected_batch.available_hour),
        "decision_revision_id": decision.decision_revision_id,
    }
    doc_specs = (
        (
            "license.json",
            {
                **common,
                "evidence_id": "license:source-scope:r1",
                "kind": "license",
                "status": "verified",
                "license_scope": "research_shadow",
                "attribution_required": True,
            },
        ),
        (
            "quality.json",
            {
                **common,
                "evidence_id": "quality:batch:r1",
                "kind": "quality",
                "status": "passed",
                "row_count": len(selected_batch.rows),
                "parser_version": selected_batch.to_dict()["parser_version"],
                "source_schema_version": selected_batch.to_dict()["source_schema_version"],
            },
        ),
        (
            "pit.json",
            {
                **common,
                "evidence_id": "pit:limitation:r1",
                "kind": "pit",
                "status": "not_established",
                "availability_basis": "captured_complete_batch_available_hour",
                "official_pit_eligible": False,
                "official_announcement_at": None,
                "reason": "official_pit_not_established",
            },
        ),
    )
    for name, payload in doc_specs:
        relative = f"documents/{name}"
        path = root / relative
        raw = _write_json(path, payload)
        documents.append(
            {"id": payload["evidence_id"], "kind": payload["kind"], "path": relative,
             "sha256": hashlib.sha256(raw).hexdigest()}
        )

    if with_unit_proof:
        proof = _unit_proof(capture.market)
        proof_path = root / "documents" / "unit-proof.json"
        write_openapi_unit_proof_artifact_create_only(proof_path, proof)
        proof_bytes = proof_path.read_bytes()
        documents.append(
            {
                "id": proof.proof_sha256,
                "kind": "unit",
                "path": "documents/unit-proof.json",
                "sha256": hashlib.sha256(proof_bytes).hexdigest(),
            }
        )

    swagger_urls = {
        "twse": "https://openapi.twse.com.tw/v1/swagger.json",
        "tpex": "https://www.tpex.org.tw/openapi/swagger.json",
    }
    dataset_ids = {"twse": "18420", "tpex": "56510"}
    supporting_specs = (
        (
            "synthetic-official-dataset",
            "official_dataset",
            f"https://data.gov.tw/dataset/{dataset_ids[capture.market]}",
            b"synthetic official dataset evidence; fixture only",
        ),
        (
            "synthetic-official-license",
            "official_license",
            "https://data.gov.tw/license",
            b"synthetic official license evidence; fixture only",
        ),
        (
            "synthetic-official-schema",
            "official_schema",
            swagger_urls[capture.market],
            b"synthetic official schema evidence; fixture only",
        ),
        (
            "synthetic-quality-qa",
            "quality_qa",
            "evidence://synthetic/isolated-qa-fixture",
            b"synthetic QA evidence; fixture only",
        ),
        (
            "synthetic-raw-capture",
            "raw_capture",
            capture.requested_url,
            capture.raw_response_bytes,
        ),
    )
    supporting_documents = []
    for evidence_id, kind, url, payload in supporting_specs:
        relative = f"supporting/{kind}.bin"
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        supporting_documents.append(
            {
                "id": evidence_id,
                "kind": kind,
                "url": url,
                "path": relative,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    binding = {
        "schema_version": MONTHLY_REVENUE_QUALIFICATION_BINDING_SCHEMA_V2,
        "source_id": source_id,
        "market": capture.market,
        "endpoint_url": capture.requested_url,
        "parser_version": selected_batch.to_dict()["parser_version"],
        "source_schema_version": selected_batch.to_dict()["source_schema_version"],
        "raw_batch_sha256": capture.raw_response_sha256,
        "captured_at": qualification_binding._datetime_text(capture.body_completed_at),
        "successful_batch_completed_at": qualification_binding._datetime_text(
            selected_batch.successful_batch_completed_at
        ),
        "available_at": qualification_binding._datetime_text(selected_batch.available_hour),
        "availability_basis": "captured_complete_batch_available_hour",
        "official_announcement_at": None,
        "official_revision_id": None,
        "decision": decision.to_dict(),
        "documents": documents,
        "supporting_documents": supporting_documents,
    }
    binding_path = root / "binding.json"
    binding_bytes = _write_json(binding_path, binding)
    return (
        PinnedMonthlyRevenueQualificationResolver(
            binding_path,
            hashlib.sha256(binding_bytes).hexdigest(),
        ),
        selected_batch,
        binding_path,
        binding,
    )


def test_pinned_resolver_projects_only_limited_research_shadow_evidence(tmp_path):
    resolver, batch, _path, _binding = _binding_fixture(tmp_path)
    evidence = resolver.evidence_for_batch(batch)

    assert evidence.source_id == batch.capture.source_id
    assert evidence.endpoint_url == batch.capture.requested_url
    assert evidence.batch_sha256 == batch.capture.raw_response_sha256
    assert evidence.available_at == batch.available_hour
    assert evidence.captured_at == batch.capture.body_completed_at
    assert evidence.source_available_at is None
    assert evidence.availability_basis == "captured_observation"
    assert evidence.official_pit_evidence_ref == ""
    assert set(evidence.source_accepted_uses) == {
        "current_research", "historical_research", "factor_research", "screening",
        "comparison", "sector_theme", "portfolio_research",
    }
    assert not set(evidence.source_accepted_uses) & {
        "scoring", "ranking", "backtest", "paper", "forward", "ml_training", "ml_validation"
    }
    assert resolver.verify(evidence, datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)) is True
    assert resolver.verify(evidence, datetime(2026, 10, 21, 8, 29, tzinfo=timezone.utc)) is False
    decision = evaluate_monthly_revenue_use(
        MonthlyRevenueUse.FACTOR_RESEARCH,
        evidence=evidence,
        cutoff_at=datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc),
        value_kind="reported_percentage",
    )
    assert decision.allowed is True
    formal = evaluate_monthly_revenue_use(
        MonthlyRevenueUse.BACKTEST,
        evidence=evidence,
        cutoff_at=datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc),
        value_kind="reported_percentage",
    )
    assert formal.allowed is False


def test_real_pinned_resolver_keeps_batch_clock_while_late_archive_controls_visibility(
    tmp_path, monkeypatch,
):
    batch = _batch()
    resolver, selected_batch, _binding_path, _binding = _binding_fixture(
        tmp_path / "qualification",
        batch=batch,
    )
    evidence = resolver.evidence_for_batch(selected_batch)
    persisted_at = datetime(2026, 10, 21, 12, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(revision_archive, "_utc_now", lambda: persisted_at)
    saved = append_monthly_revenue_batch(
        tmp_path / "archive",
        raw_batch_from_openapi(selected_batch),
        archive_sha256=None,
        expected_archive_sha256=None,
    )
    archive = read_monthly_revenue_revision_archive(
        tmp_path / "archive",
        saved.archive_sha256,
        expected_archive_sha256=saved.archive_sha256,
    )
    verify_calls = []

    def verify(candidate, cutoff_at):
        verify_calls.append((candidate, cutoff_at))
        return resolver.verify(candidate, cutoff_at)

    service = MonthlyRevenueResearchService(qualification_verifier=verify)
    before = service.archived_observation_as_of(
        archive,
        expected_archive_sha256=saved.archive_sha256,
        market="twse",
        stock_code="2330",
        period="2026-09",
        metric="revenue_yoy_percent",
        evidence=evidence,
        cutoff_at=datetime(2026, 10, 21, 12, 59, tzinfo=timezone.utc),
    )
    after_cutoff = datetime(2026, 10, 21, 13, 0, tzinfo=timezone.utc)
    after = service.archived_observation_as_of(
        archive,
        expected_archive_sha256=saved.archive_sha256,
        market="twse",
        stock_code="2330",
        period="2026-09",
        metric="revenue_yoy_percent",
        evidence=evidence,
        cutoff_at=after_cutoff,
    )
    backtest = service.project_decision_cutoff(
        archive,
        expected_archive_sha256=saved.archive_sha256,
        market="twse",
        stock_code="2330",
        period="2026-09",
        metric="revenue_yoy_percent",
        evidence=evidence,
        decision_cutoff_at=after_cutoff,
        purpose="backtest",
    )
    rebound_evidence = replace(
        evidence,
        available_at=evidence.available_at + timedelta(hours=1),
    )
    rebound = service.archived_observation_as_of(
        archive,
        expected_archive_sha256=saved.archive_sha256,
        market="twse",
        stock_code="2330",
        period="2026-09",
        metric="revenue_yoy_percent",
        evidence=rebound_evidence,
        cutoff_at=after_cutoff,
    )

    assert before.status == "not_visible_by_cutoff" and before.fact is None
    assert after.status == "PASS" and after.fact is not None and after.fact.allowed
    assert after.fact.evidence is evidence
    assert after.fact.source_batch_available_at == evidence.available_at
    assert after.fact.available_at == after_cutoff
    assert after.fact.available_at > evidence.available_at
    assert backtest.status == "BLOCKED_WITH_REASON"
    assert backtest.fact is not None and not backtest.fact.allowed
    assert not backtest.formal_pit_eligible
    assert "archive_observation_is_not_formal_pit" in backtest.reasons
    assert rebound.status == "source_evidence_mismatch" and rebound.fact is None
    assert verify_calls == [(evidence, after_cutoff), (evidence, after_cutoff)]


def test_resolver_rejects_other_batch_and_unissued_or_modified_evidence(tmp_path):
    resolver, batch, _path, _binding = _binding_fixture(tmp_path)
    evidence = resolver.evidence_for_batch(batch)
    with pytest.raises(MonthlyRevenueQualificationBindingError, match="batch_binding_identity_mismatch"):
        resolver.evidence_for_batch(_batch(amount="9.999"))

    changed = replace(evidence, acceptance_evidence_ref="sha256:" + "0" * 64)
    assert resolver.verify(changed, datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)) is False
    fresh_resolver, _batch_again, _path_again, _binding_again = _binding_fixture(
        tmp_path / "other"
    )
    assert fresh_resolver.verify(evidence, datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)) is False


def test_resolver_freshly_rechecks_pinned_evidence_artifacts(tmp_path):
    resolver, batch, _path, _binding = _binding_fixture(tmp_path)
    evidence = resolver.evidence_for_batch(batch)
    quality_path = tmp_path / "documents" / "quality.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    quality["status"] = "failed"
    quality_path.write_bytes(_canonical_bytes(quality))
    assert resolver.verify(evidence, datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)) is False

    _fresh_resolver, fresh_batch, fresh_binding_path, fresh_binding = _binding_fixture(
        tmp_path / "identity"
    )
    tampered_binding = dict(fresh_binding)
    tampered_binding["available_at"] = "2026-10-21T09:00:00+00:00"
    binding_path = fresh_binding_path.parent / "tampered-binding.json"
    raw = _write_json(binding_path, tampered_binding)
    tampered_resolver = PinnedMonthlyRevenueQualificationResolver(
        binding_path,
        hashlib.sha256(raw).hexdigest(),
    )
    with pytest.raises(MonthlyRevenueQualificationBindingError, match="binding_document_identity_mismatch"):
        tampered_resolver.evidence_for_batch(fresh_batch)


def test_future_acceptance_and_nonapplying_decisions_never_qualify(tmp_path):
    resolver, batch, _path, _binding = _binding_fixture(
        tmp_path / "future",
        decided_at="2026-10-21T09:00:00+00:00",
    )
    evidence = resolver.evidence_for_batch(batch)
    assert resolver.verify(evidence, datetime(2026, 10, 21, 8, 59, tzinfo=timezone.utc)) is False
    assert resolver.verify(evidence, datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)) is True

    deferred, deferred_batch, _path, _binding = _binding_fixture(
        tmp_path / "deferred",
        decision_status="deferred",
    )
    with pytest.raises(
        MonthlyRevenueQualificationBindingError,
        match="binding_decision_not_limited_research_shadow",
    ):
        deferred.evidence_for_batch(deferred_batch)


def test_unit_proof_is_reopened_and_bound_to_market_endpoint_and_batch(tmp_path):
    resolver, batch, _path, _binding = _binding_fixture(
        tmp_path,
        with_unit_proof=True,
    )
    evidence = resolver.evidence_for_batch(batch)
    assert evidence.unit_proof_sha256 is not None
    assert evidence.unit_proof_sha256 == batch.unit_proof_sha256
    assert resolver.verify(evidence, datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)) is True


def test_binding_rejects_path_traversal_even_when_manifest_is_repinned(tmp_path):
    resolver, batch, binding_path, _binding = _binding_fixture(tmp_path)
    evidence = resolver.evidence_for_batch(batch)
    changed = json.loads(binding_path.read_text(encoding="utf-8"))
    changed["documents"][0]["path"] = "../outside.json"
    raw = _write_json(tmp_path / "traversal.json", changed)
    traversing = PinnedMonthlyRevenueQualificationResolver(
        tmp_path / "traversal.json",
        hashlib.sha256(raw).hexdigest(),
    )
    with pytest.raises(
        MonthlyRevenueQualificationBindingError,
        match="binding_document_path_must_be_safe_relative",
    ):
        traversing.evidence_for_batch(batch)
    assert resolver.verify(evidence, datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)) is True


def test_binding_file_hardlink_is_rejected(tmp_path):
    _resolver, batch, binding_path, _binding = _binding_fixture(tmp_path)
    alias = tmp_path / "binding-alias.json"
    try:
        os.link(binding_path, alias)
    except OSError as exc:
        pytest.skip(f"hardlink fixture unsupported: {exc}")
    resolver = PinnedMonthlyRevenueQualificationResolver(
        alias,
        hashlib.sha256(binding_path.read_bytes()).hexdigest(),
    )
    with pytest.raises(
        MonthlyRevenueQualificationBindingError,
        match="binding_file_type_or_size_invalid",
    ):
        resolver.evidence_for_batch(batch)


def test_resolver_rechecks_every_pinned_supporting_document_on_verify(tmp_path):
    resolver, batch, _path, _binding = _binding_fixture(tmp_path)
    evidence = resolver.evidence_for_batch(batch)
    support_path = tmp_path / "supporting" / "official_dataset.bin"
    support_path.write_bytes(b"changed synthetic dataset evidence")
    assert resolver.verify(
        evidence, datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
    ) is False


@pytest.mark.parametrize(
    ("override", "expected_reason"),
    [
        ("wrong_dataset_market", "binding_supporting_document_official_dataset_url_mismatch"),
        ("raw_capture_sha", "binding_supporting_document_raw_capture_sha256_mismatch"),
        ("missing_license", "binding_supporting_document_required_reference_missing"),
    ],
)
def test_resolver_rejects_supporting_identity_and_required_reference_drift(
    tmp_path, override, expected_reason
):
    resolver, batch, binding_path, _binding = _binding_fixture(tmp_path)
    evidence = resolver.evidence_for_batch(batch)
    changed = json.loads(binding_path.read_text(encoding="utf-8"))
    supports = changed["supporting_documents"]
    if override == "wrong_dataset_market":
        dataset = next(item for item in supports if item["kind"] == "official_dataset")
        dataset["url"] = "https://data.gov.tw/dataset/56510"
    elif override == "raw_capture_sha":
        capture_doc = next(item for item in supports if item["kind"] == "raw_capture")
        changed_bytes = b"wrong raw capture fixture bytes"
        capture_path = tmp_path / capture_doc["path"]
        capture_path.write_bytes(changed_bytes)
        capture_doc["sha256"] = hashlib.sha256(changed_bytes).hexdigest()
    else:
        changed["supporting_documents"] = [
            item for item in supports if item["kind"] != "official_license"
        ]
    repinned_path = tmp_path / f"{override}.json"
    repinned_bytes = _write_json(repinned_path, changed)
    repinned = PinnedMonthlyRevenueQualificationResolver(
        repinned_path,
        hashlib.sha256(repinned_bytes).hexdigest(),
    )
    with pytest.raises(MonthlyRevenueQualificationBindingError, match=expected_reason):
        repinned.evidence_for_batch(batch)
    original_binding_remains_valid = override != "raw_capture_sha"
    assert resolver.verify(
        evidence, datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
    ) is original_binding_remains_valid


def test_supporting_manifest_is_bounded_by_count_and_file_size(tmp_path):
    _resolver, batch, binding_path, _binding = _binding_fixture(tmp_path)
    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    supports = binding["supporting_documents"]
    binding["supporting_documents"] = supports + [
        {**supports[0], "id": f"synthetic-extra-{index}"}
        for index in range(4)
    ]
    too_many_path = tmp_path / "too-many-supports.json"
    too_many_bytes = _write_json(too_many_path, binding)
    too_many = PinnedMonthlyRevenueQualificationResolver(
        too_many_path, hashlib.sha256(too_many_bytes).hexdigest()
    )
    with pytest.raises(
        MonthlyRevenueQualificationBindingError,
        match="binding_supporting_documents_invalid",
    ):
        too_many.evidence_for_batch(batch)

    _resolver, batch, binding_path, _binding = _binding_fixture(tmp_path / "large")
    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    dataset = next(
        item for item in binding["supporting_documents"]
        if item["kind"] == "official_dataset"
    )
    payload = b"x" * (
        qualification_binding.MONTHLY_REVENUE_QUALIFICATION_DOCUMENT_MAX_BYTES + 1
    )
    dataset_path = tmp_path / "large" / dataset["path"]
    dataset_path.write_bytes(payload)
    dataset["sha256"] = hashlib.sha256(payload).hexdigest()
    large_path = tmp_path / "large" / "repinned-large.json"
    large_bytes = _write_json(large_path, binding)
    large = PinnedMonthlyRevenueQualificationResolver(
        large_path, hashlib.sha256(large_bytes).hexdigest()
    )
    with pytest.raises(
        MonthlyRevenueQualificationBindingError,
        match="binding_supporting_document_file_type_or_size_invalid",
    ):
        large.evidence_for_batch(batch)
def test_issued_evidence_cache_has_a_fixed_bound(tmp_path):
    resolver, batch, _path, _binding = _binding_fixture(tmp_path)
    issued = [resolver.evidence_for_batch(batch) for _ in range(
        qualification_binding.MONTHLY_REVENUE_QUALIFICATION_ISSUED_EVIDENCE_MAX_COUNT + 1
    )]
    assert len(resolver._issued) == qualification_binding.MONTHLY_REVENUE_QUALIFICATION_ISSUED_EVIDENCE_MAX_COUNT
    assert resolver.verify(
        issued[0], datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
    ) is False
    assert resolver.verify(
        issued[-1], datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
    ) is True
