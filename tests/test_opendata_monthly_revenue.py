from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, localcontext
import json
import hashlib
import sqlite3
from pathlib import Path

import pytest

from data_module.current_fundamental_snapshots import (
    TABLE,
    _derived_monthly_source_version,
    ensure_current_observation_schema,
    insert_observations,
    normalize_current_observation,
)
from data_module.opendata_monthly_revenue import (
    OPENAPI_MONTHLY_REVENUE_ENDPOINTS,
    OPENAPI_MONTHLY_REVENUE_SOURCE_IDS,
    OpenApiMonthlyRevenueCapture,
    OpenApiMonthlyRevenueError,
    OpenApiMonthlyRevenueUnitProof,
    build_openapi_monthly_revenue_pair_approval_request,
    build_openapi_unit_field_map_bytes,
    openapi_batch_to_current_observations,
    prepare_openapi_monthly_revenue_batch,
    write_openapi_unit_proof_artifact_create_only,
    verify_openapi_snapshot_raw_batch,
)
from data_module.daily_source_snapshot import (
    DAILY_SOURCE_SNAPSHOT_DATASET_ID,
    DAILY_SOURCE_SNAPSHOT_SOURCE_ID,
    DAILY_SOURCE_TIME_BASIS_POLICY,
    DailySourceBatchValidation,
    DailySourceSnapshot,
    DailySourceSnapshotFileReader,
    DailySourceSnapshotRecord,
    DailySourceTransportCapture,
    DailySourceUseAcceptance,
    DailySourceUseScope,
    DailySourceValidationCheck,
    write_daily_source_snapshot,
    _availability_for_record,
    _completion_clock_sample,
    _validate_supported_scope,
    _validate_transport_capture_for_snapshot,
    DailySourceSnapshotError,
)
from data_module.recommendation_current_fundamental_provider import (
    RecommendationCurrentFundamentalProvider,
)
from data_module.daily_monthly_revenue_cohort_binding import _validate_current_scope
from data_module.daily_monthly_revenue_cohort import (
    build_daily_monthly_revenue_cohort_pin,
    write_daily_monthly_revenue_cohort_pin_create_only,
)
from data_module.daily_monthly_revenue_cohort_binding import (
    read_daily_monthly_revenue_cohort_binding,
    serialize_daily_monthly_revenue_cohort_binding,
)


BODY_AT = datetime(2026, 10, 21, 7, 15, tzinfo=timezone.utc)
OBSERVED_AT = datetime(2026, 10, 21, 7, 20, tzinfo=timezone.utc)


def _source_row(code: str, amount: str) -> dict[str, str]:
    return {
        "資料年月": "11509",
        "公司代號": code,
        "公司名稱": f"隔離測試公司{code}",
        "營業收入-當月營收": amount,
        "營業收入-上月營收": "10",
        "營業收入-去年當月營收": "8",
        "營業收入-上月比較增減(%)": "",
        "營業收入-去年同月增減(%)": "",
        "累計營業收入-當月累計營收": "20",
        "累計營業收入-去年累計營收": "16",
        "累計營業收入-前期比較增減(%)": "",
        "出表日期": "1151010",
        "備註": "隔離 fixture",
        "產業別": "測試業",
    }


def _capture(market: str = "twse", rows: list[dict[str, str]] | None = None):
    body = json.dumps(
        rows or [_source_row("2330", "1.250"), _source_row("2317", "2.500")],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    endpoint = OPENAPI_MONTHLY_REVENUE_ENDPOINTS[market]
    return OpenApiMonthlyRevenueCapture(
        market=market,
        requested_url=endpoint,
        response_url=endpoint,
        response_status=200,
        content_type_original_text="application/json; charset=utf-8",
        content_encoding_original_text="identity",
        content_length_original_text=str(len(body)),
        response_body_complete=True,
        eof_observed=True,
        received_body_bytes=len(body),
        body_observation_ended_at=BODY_AT,
        body_completed_at=BODY_AT,
        raw_response_bytes=body,
    )


def _unit_proof(market: str = "twse") -> OpenApiMonthlyRevenueUnitProof:
    document = (
        f"isolated fixture document for {market}; unit 仟元; not an official source"
    ).encode("utf-8")
    document_sha = hashlib.sha256(document).hexdigest()
    document_url = f"https://data.gov.tw/dataset/{'18420' if market == 'twse' else '56510'}"
    field_map = build_openapi_unit_field_map_bytes(
        market=market,
        official_document_url=document_url,
        official_document_sha256=document_sha,
    )
    return OpenApiMonthlyRevenueUnitProof(
        market=market,
        source_id=OPENAPI_MONTHLY_REVENUE_SOURCE_IDS[market],
        endpoint_url=OPENAPI_MONTHLY_REVENUE_ENDPOINTS[market],
        official_document_url=document_url,
        official_document_bytes=document,
        official_document_sha256=document_sha,
        field_map_bytes=field_map,
        field_map_sha256=hashlib.sha256(field_map).hexdigest(),
        trusted_evidence_scope_id="isolated-fixture:exact-source-field-map",
        source_unit_original_text="仟元",
        conversion_to_twd=Decimal("1000"),
    )


def test_full_batch_is_deterministic_and_preserves_source_units_until_exact_proof_pin():
    capture = _capture()
    batch = prepare_openapi_monthly_revenue_batch(
        capture=capture,
        successful_batch_completed_at=BODY_AT,
    )
    assert tuple(row.stock_code for row in batch.rows) == ("2317", "2330")
    assert dict(batch.rows[1].amount_values_source_unit)["營業收入-當月營收"] == Decimal("1.250")
    assert batch.conversion_to_twd is None
    assert batch.unit_proof_sha256 is None
    assert batch.canonical_bytes() == prepare_openapi_monthly_revenue_batch(
        capture=capture,
        successful_batch_completed_at=BODY_AT,
    ).canonical_bytes()
    with pytest.raises(OpenApiMonthlyRevenueError, match="trusted_unit_proof_required"):
        openapi_batch_to_current_observations(batch, observed_at=OBSERVED_AT)


def test_exact_unit_proof_pin_builds_existing_verified_observation_shape():
    capture = _capture()
    proof = _unit_proof()
    batch = prepare_openapi_monthly_revenue_batch(
        capture=capture,
        successful_batch_completed_at=BODY_AT,
        unit_proof=proof,
        trusted_unit_proof_sha256=proof.proof_sha256,
    )
    rows = openapi_batch_to_current_observations(batch, observed_at=OBSERVED_AT)
    assert len(rows) == 2
    assert rows[1]["source"] == OPENAPI_MONTHLY_REVENUE_SOURCE_IDS["twse"]
    assert rows[1]["value"] == "1250.000"
    normalized = normalize_current_observation(rows[1])
    assert normalized["basis_verified"] == "1"
    assert normalized["unit"] == "TWD"
    with localcontext() as context:
        context.prec = 2
        candidate_rows = batch.to_dict()["rows"]
        assert candidate_rows[1]["amount_values_twd"]["營業收入-當月營收"] == "1250.000"
        context_rows = openapi_batch_to_current_observations(
            batch, observed_at=OBSERVED_AT
        )
        assert context_rows[1]["value"] == "1250.000"


def test_unit_conversion_rejects_unpinned_or_cross_market_proof():
    proof = _unit_proof()
    unpinned = prepare_openapi_monthly_revenue_batch(
        capture=_capture(),
        successful_batch_completed_at=BODY_AT,
        unit_proof=proof,
        trusted_unit_proof_sha256="0" * 64,
    )
    assert unpinned.conversion_to_twd is None
    with pytest.raises(OpenApiMonthlyRevenueError, match="trusted_unit_proof_required"):
        openapi_batch_to_current_observations(unpinned, observed_at=OBSERVED_AT)

    with pytest.raises(OpenApiMonthlyRevenueError, match="unit_proof_does_not_match_capture"):
        prepare_openapi_monthly_revenue_batch(
            capture=_capture("tpex"),
            successful_batch_completed_at=BODY_AT,
            unit_proof=proof,
            trusted_unit_proof_sha256=proof.proof_sha256,
        )


def test_full_batch_rejects_duplicate_and_mixed_period_rows():
    with pytest.raises(OpenApiMonthlyRevenueError, match="duplicate_stock_code"):
        prepare_openapi_monthly_revenue_batch(
            capture=_capture(rows=[_source_row("2330", "1"), _source_row("2330", "2")]),
            successful_batch_completed_at=BODY_AT,
        )

    mixed = _source_row("2317", "2")
    mixed["資料年月"] = "11508"
    with pytest.raises(OpenApiMonthlyRevenueError, match="multiple_periods"):
        prepare_openapi_monthly_revenue_batch(
            capture=_capture(rows=[_source_row("2330", "1"), mixed]),
            successful_batch_completed_at=BODY_AT,
        )


def test_pending_pair_approval_never_creates_accepted_at():
    request = json.loads(build_openapi_monthly_revenue_pair_approval_request())
    assert request["approval_status"] == "pending_owner_decision"
    assert request["source_acceptance_created"] is False
    assert request["accepted_at"] is None
    assert tuple(source["source_id"] for source in request["sources"]) == (
        OPENAPI_MONTHLY_REVENUE_SOURCE_IDS["twse"],
        OPENAPI_MONTHLY_REVENUE_SOURCE_IDS["tpex"],
    )


def _snapshot(
    tmp_path: Path,
    *,
    proof_hash: str | None,
    tampered_code: bool = False,
    market: str = "twse",
) -> DailySourceSnapshot:
    tmp_path.mkdir(parents=True, exist_ok=True)
    capture = _capture(market)
    batch = prepare_openapi_monthly_revenue_batch(
        capture=capture, successful_batch_completed_at=BODY_AT
    )
    scope = DailySourceUseScope(
        dataset_id="fundamental_current_observations.monthly_revenue",
        source_id=OPENAPI_MONTHLY_REVENUE_SOURCE_IDS[market],
        market=market,
        parser_version="twse-tpex-openapi-monthly-revenue-parser.v1",
        source_schema_version="twse-tpex-openapi-monthly-revenue-14-fields.v1",
        unit="TWD",
        intended_use="recommendation_current_fundamental",
    )
    chain = ("isolated-fixture:never-formal-acceptance",)
    if proof_hash:
        proof = _unit_proof(market)
        proof_path = tmp_path / f"unit-proof-{market}.json"
        write_openapi_unit_proof_artifact_create_only(proof_path, proof)
        chain = (
            f"unit-proof-sha256:{proof_hash}",
            f"unit-proof-artifact:{proof_path}",
            proof.official_document_url,
        )
    acceptance = DailySourceUseAcceptance(
        scope=scope,
        acceptance_id="isolated-opendata-acceptance-fixture",
        accepted_at=datetime(2026, 10, 21, 6, 0, tzinfo=timezone.utc),
        official_source_endpoint=OPENAPI_MONTHLY_REVENUE_ENDPOINTS[market],
        document_chain=chain,
        acceptance_evidence_ref="isolated-fixture:never-formal-acceptance",
        authorization_scope="recommendation_current_fundamental only",
    )
    digest = capture.raw_response_sha256
    records = tuple(
        DailySourceSnapshotRecord(
            stock_code=("9999" if tampered_code and index == 0 else row.stock_code),
            market=market,
            period=batch.period,
            source_version=row.source_version,
            raw_source_sha256=digest,
            unit="TWD",
        )
        for index, row in enumerate(batch.rows)
    )
    def passed(check_id: str) -> DailySourceValidationCheck:
        return DailySourceValidationCheck(check_id, "pass", f"{check_id}_fixture_pass")

    validation = DailySourceBatchValidation(
        validation_id="isolated-opendata-batch-validation",
        expected_partition_ids=("twse-openapi-monthly-revenue",),
        successful_partition_ids=("twse-openapi-monthly-revenue",),
        failed_partition_ids=(),
        expected_record_count=len(records),
        actual_record_count=len(records),
        source_status_check=passed("source_status"),
        raw_source_hash_check=passed("raw_source_hash"),
        schema_check=passed("schema"),
        unit_check=passed("unit"),
        finite_values_check=passed("finite_values"),
        missing_values_check=passed("missing_values"),
        prior_period_required_check=DailySourceValidationCheck(
            "prior_period_required", "not_required", "prior_period_not_required"
        ),
        official_timestamp_parse_check=DailySourceValidationCheck(
            "official_timestamp_parse", "not_required", "official_timestamp_not_provided"
        ),
    )
    sample = datetime(2026, 10, 21, 7, 20, tzinfo=timezone.utc)
    root = tmp_path / "snapshots"
    write_daily_source_snapshot(
        root,
        batch_id=f"isolated-opendata-{market}",
        scope=scope,
        use_acceptance=acceptance,
        source_batch_started_at=datetime(2026, 10, 21, 7, 10, tzinfo=timezone.utc),
        raw_source_bytes=capture.raw_response_bytes,
        records=records,
        validation=validation,
        transport_capture=capture.to_daily_source_transport_capture(),
        clock=lambda: sample,
    )
    return DailySourceSnapshotFileReader(root, trusted_acceptance=acceptance).read_snapshot(
        f"isolated-opendata-{market}", expected_scope=scope
    )


def test_pinned_snapshot_reader_reparses_entire_raw_batch_and_checks_unit_anchor(tmp_path: Path):
    proof = _unit_proof()
    snapshot = _snapshot(tmp_path / "valid", proof_hash=proof.proof_sha256)
    values = verify_openapi_snapshot_raw_batch(snapshot)
    assert values == {"2317": Decimal("2500.000"), "2330": Decimal("1250.000")}

    with pytest.raises(OpenApiMonthlyRevenueError, match="exact_unit_proof_pin_missing"):
        verify_openapi_snapshot_raw_batch(_snapshot(tmp_path / "no-proof", proof_hash=None))
    with pytest.raises(OpenApiMonthlyRevenueError, match="recordset_differs_from_raw"):
        verify_openapi_snapshot_raw_batch(
            _snapshot(tmp_path / "tampered", proof_hash=proof.proof_sha256, tampered_code=True)
        )


def test_snapshot_scope_allows_only_exact_openapi_market_endpoint_and_keeps_mops_scope():
    _validate_supported_scope(
        DailySourceUseScope(
            dataset_id="fundamental_current_observations.monthly_revenue",
            source_id="mops.monthly_revenue_static_snapshot",
            market="twse",
            parser_version="legacy-parser.v1",
            source_schema_version="legacy-schema.v1",
            unit="source-unit",
            intended_use="research_current_use",
        )
    )
    wrong_pair = DailySourceUseScope(
        dataset_id="fundamental_current_observations.monthly_revenue",
        source_id=OPENAPI_MONTHLY_REVENUE_SOURCE_IDS["twse"],
        market="tpex",
        parser_version="twse-tpex-openapi-monthly-revenue-parser.v1",
        source_schema_version="twse-tpex-openapi-monthly-revenue-14-fields.v1",
        unit="TWD",
        intended_use="recommendation_current_fundamental",
    )
    with pytest.raises(DailySourceSnapshotError, match="exact MOPS/OpenData profiles"):
        _validate_supported_scope(wrong_pair)


def test_existing_mops_scope_rejects_new_opendata_json_transport_profile():
    endpoint = "https://mops.twse.com.tw/mops/web/t05st10_ifrs"
    raw = b"[]"
    scope = DailySourceUseScope(
        dataset_id=DAILY_SOURCE_SNAPSHOT_DATASET_ID,
        source_id=DAILY_SOURCE_SNAPSHOT_SOURCE_ID,
        market="twse",
        parser_version="mops-monthly-parser.v2",
        source_schema_version="mops-monthly-schema.v2",
        unit="TWD",
        intended_use="recommendation_current_fundamental",
    )
    acceptance = DailySourceUseAcceptance(
        scope=scope,
        acceptance_id="isolated-mops-json-rejection",
        accepted_at=datetime(2026, 10, 21, 6, 0, tzinfo=timezone.utc),
        official_source_endpoint=endpoint,
        document_chain=(endpoint,),
        acceptance_evidence_ref="isolated-fixture:never-formal-acceptance",
        authorization_scope="recommendation_current_fundamental only",
    )
    capture = DailySourceTransportCapture(
        raw_response_bytes=raw,
        official_source_url=endpoint,
        response_status=200,
        content_type="application/json; charset=utf-8",
        declared_decoding_encoding="utf-8",
        decoding_basis="rfc8259_utf8",
        body_completed_at=BODY_AT,
        transport_sha256=hashlib.sha256(raw).hexdigest(),
        response_body_complete=True,
        received_body_bytes=len(raw),
        content_length_original_text=str(len(raw)),
        body_completion_evidence_ref="eof:isolated-json-fixture",
        response_url=endpoint,
        content_encoding_original_text="identity",
        eof_observed=True,
        body_observation_ended_at=BODY_AT,
    )
    with pytest.raises(
        DailySourceSnapshotError,
        match="MOPS snapshot transport must retain the existing HTML charset profile",
    ):
        _validate_transport_capture_for_snapshot(
            transport_capture=capture,
            use_acceptance=acceptance,
            source_batch_started_at=datetime(2026, 10, 21, 7, 10, tzinfo=timezone.utc),
            first_persisted_at=None,
            successful_batch_completed_at=None,
            raw_source_bytes=raw,
            raw_source_sha256=hashlib.sha256(raw).hexdigest(),
            records=(),
        )


@pytest.mark.parametrize(
    ("market", "source_id"),
    (
        ("twse", "twse.openapi.t187ap05_L"),
        ("tpex", "tpex.openapi.mopsfin_t187ap05_O"),
    ),
)
def test_existing_binding_scope_validator_accepts_only_named_opendata_market_profile(
    market: str, source_id: str
):
    _validate_current_scope(
        DailySourceUseScope(
            dataset_id="fundamental_current_observations.monthly_revenue",
            source_id=source_id,
            market=market,
            parser_version="twse-tpex-openapi-monthly-revenue-parser.v1",
            source_schema_version="twse-tpex-openapi-monthly-revenue-14-fields.v1",
            unit="TWD",
            intended_use="recommendation_current_fundamental",
        ),
        market,
    )


def test_existing_provider_reader_accepts_only_raw_reconciled_opendata_after_availability(
    tmp_path: Path,
):
    proof = _unit_proof()
    snapshot = _snapshot(tmp_path / "provider", proof_hash=proof.proof_sha256)

    class _PinnedSnapshotReader:
        def read_snapshot(self, batch_id: str, *, expected_scope: DailySourceUseScope):
            assert batch_id == snapshot.batch_id
            if expected_scope != snapshot.scope:
                raise ValueError("快照來源用途範圍與呼叫端預期不符")
            return snapshot

    rows = openapi_batch_to_current_observations(
        prepare_openapi_monthly_revenue_batch(
            capture=_capture(),
            successful_batch_completed_at=BODY_AT,
            unit_proof=proof,
            trusted_unit_proof_sha256=proof.proof_sha256,
        ),
        observed_at=OBSERVED_AT,
    )
    database = tmp_path / "current-observations.sqlite"
    with sqlite3.connect(database) as connection:
        ensure_current_observation_schema(connection)
        assert insert_observations(connection, rows) == len(rows)

    provider = RecommendationCurrentFundamentalProvider(
        db_file=database,
        output_root=tmp_path / "unused-output",
        daily_source_snapshot_reader=_PinnedSnapshotReader(),
    )
    before = provider.load_monthly_revenues(
        stock_code="2330",
        cutoff_at=datetime(2026, 10, 21, 7, 59, 59, tzinfo=timezone.utc),
        pinned_daily_batch_id=snapshot.batch_id,
    )
    available = provider.load_monthly_revenues(
        stock_code="2330",
        cutoff_at=datetime(2026, 10, 21, 8, 1, tzinfo=timezone.utc),
        pinned_daily_batch_id=snapshot.batch_id,
    )
    assert before.status == "missing"
    assert available.status == "ready"
    assert available.observations[0].revenue == Decimal("1250.000")
    assert available.observations[0].raw_source_version == snapshot.records[1].source_version

    drifted_version = _derived_monthly_source_version(
        snapshot.records[1].source_version,
        stock_code="2330",
        period="2026-09",
        value="1251",
        unit="TWD",
        source_available_at=BODY_AT.isoformat(),
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            f"UPDATE {TABLE} SET value=?, source_version=? WHERE stock_code=? AND item_code='revenue'",
            ("1251", drifted_version, "2330"),
        )
    drifted = provider.load_monthly_revenues(
        stock_code="2330",
        cutoff_at=datetime(2026, 10, 21, 8, 1, tzinfo=timezone.utc),
        pinned_daily_batch_id=snapshot.batch_id,
    )
    assert drifted.status == "missing"
    assert any("differs_from_raw_response" in item for item in drifted.diagnostics)


def test_public_snapshot_to_cohort_binding_roundtrip_revalidates_both_markets(
    tmp_path: Path,
):
    readers = {}
    batch_ids = {}
    for market in ("twse", "tpex"):
        proof = _unit_proof(market)
        snapshot = _snapshot(
            tmp_path / market,
            proof_hash=proof.proof_sha256,
            market=market,
        )
        readers[market] = DailySourceSnapshotFileReader(
            tmp_path / market / "snapshots",
            trusted_acceptance=snapshot.use_acceptance,
        )
        batch_ids[market] = snapshot.batch_id

    pin = build_daily_monthly_revenue_cohort_pin(
        period="2026-09",
        required_markets=("twse", "tpex"),
        batch_ids=batch_ids,
        readers=readers,
    )
    pin_root = tmp_path / "cohort-pins"
    pin_root.mkdir()
    write_daily_monthly_revenue_cohort_pin_create_only(pin_root, pin)
    binding = serialize_daily_monthly_revenue_cohort_binding(
        cohort_pin_root=pin_root,
        pin=pin,
        market_readers=readers,
    )
    binding_path = tmp_path / "cohort-binding.json"
    with binding_path.open("xb") as handle:
        handle.write(binding)
    result = read_daily_monthly_revenue_cohort_binding(
        binding_path,
        expected_binding_sha256=hashlib.sha256(binding).hexdigest(),
    )
    result.verify_cohort()
