from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path

import data_module.pit_sector_membership_reader as reader_module
from data_module.pit_sector_membership_machine import build_machine_pit_publication
from data_module.pit_sector_membership_reader import PITSectorMembershipReader

from tests.pit_test_support import (
    DECISION_AT,
    _file_hash,
    _sha256_json,
    build_pit_fixture,
    load_json,
    write_json,
)


def _read(fixture, *, decision_at=DECISION_AT, market_scope=None):
    return PITSectorMembershipReader([fixture.artifact_path]).read(
        as_of_date=date(2026, 8, 25),
        decision_at=decision_at,
        market_scope=market_scope,
    )


def test_reader_accepts_existing_producer_sidecar_with_complete_custody_fixture(tmp_path: Path) -> None:
    fixture = build_pit_fixture(tmp_path, symbols=("2330",))

    result = _read(fixture)

    assert result.status == "accepted"
    assert result.industry_filter_usable is True
    assert result.rows[0].symbol == "2330"
    assert result.rows[0].industry_category == "半導體業"
    assert result.rows[0].security_type == "common_equity"
    assert result.lineage["raw_custody_verified"] is True
    assert result.lineage["universe_verified"] is True
    assert result.lineage["taxonomy_verified"] is True
    assert result.lineage["classification_version"] == "tw-industry-code-map.v1"
    # The existing sidecar producer intentionally leaves these optional row
    # fields out; the separate versioned taxonomy identity supplies them.
    assert "membership_classification_version_missing" in result.warnings
    assert "membership_security_type_unrecorded" in result.warnings


def test_reader_rejects_score_identity_tamper_even_when_declared_hash_is_unchanged(
    tmp_path: Path,
) -> None:
    fixture = build_pit_fixture(tmp_path, symbols=("2330",))
    identity = load_json(fixture.universe_identity_path)
    assert isinstance(identity, dict)
    identity["scores_bp"] = [9999]
    write_json(fixture.universe_identity_path, identity)

    result = _read(fixture)

    assert result.status == "unavailable"
    assert result.lineage["universe_verified"] is False
    assert "universe_identity_hash_reconstruction_mismatch" in result.warnings


def test_reader_rejects_symbol_identity_tamper_and_empty_or_wrong_schema(
    tmp_path: Path,
) -> None:
    fixture = build_pit_fixture(tmp_path, symbols=("2330",))
    identity = load_json(fixture.universe_identity_path)
    assert isinstance(identity, dict)
    identity["symbols"] = ["1101"]
    write_json(fixture.universe_identity_path, identity)
    altered_symbols = _read(fixture)
    assert altered_symbols.status == "unavailable"
    assert "universe_identity_hash_reconstruction_mismatch" in altered_symbols.warnings
    assert "universe_identity_symbols_mismatch" in altered_symbols.warnings

    write_json(fixture.universe_identity_path, {})
    empty_identity = _read(fixture)
    assert empty_identity.status == "unavailable"
    assert "universe_identity_schema_invalid" in empty_identity.warnings
    assert "universe_identity_scores_missing_for_hash_reconstruction" in empty_identity.warnings

    write_json(
        fixture.universe_identity_path,
        {
            "schema_version": "wrong-universe-schema.v1",
            "symbols": ["2330"],
            "scores_bp": [8000],
            "universe_hash": "sha256:" + "0" * 64,
            "candidate_count": 1,
            "source_id": "daily_prices",
        },
    )
    wrong_schema = _read(fixture)
    assert wrong_schema.status == "unavailable"
    assert "universe_identity_schema_invalid" in wrong_schema.warnings


def test_reader_normalizes_decision_offset_before_future_date_gate(tmp_path: Path) -> None:
    fixture = build_pit_fixture(tmp_path, symbols=("2330",))

    utc_same_instant = _read(fixture, decision_at="2026-08-25T00:30:00+00:00")
    taipei_same_instant = _read(fixture, decision_at="2026-08-25T08:30:00+08:00")
    future = PITSectorMembershipReader([fixture.artifact_path]).read(
        as_of_date=date(2026, 8, 26),
        decision_at="2026-08-24T16:30:00+00:00",
    )

    assert utc_same_instant.status == taipei_same_instant.status == "accepted"
    assert utc_same_instant.decision_at == taipei_same_instant.decision_at
    assert future.status == "unavailable"
    assert "pit_as_of_after_decision_date" in future.warnings


def test_taxonomy_missing_unknown_code_and_partial_denominator_never_verify_filter(
    tmp_path: Path,
) -> None:
    missing_fixture = build_pit_fixture(
        tmp_path / "missing",
        symbols=("2330",),
        include_taxonomy=False,
    )
    missing = _read(missing_fixture)
    assert missing.status == "accepted"
    assert missing.usable is True
    assert missing.industry_filter_usable is False
    assert "membership_taxonomy_identity_missing" in missing.warnings

    unknown_fixture = build_pit_fixture(tmp_path / "unknown", symbols=("2330",))
    taxonomy = load_json(unknown_fixture.taxonomy_identity_path)
    assert isinstance(taxonomy, dict)
    taxonomy["mapping"] = {"01": "水泥工業"}
    from tests.pit_test_support import _sha256_json

    body = dict(taxonomy)
    body.pop("mapping_hash", None)
    taxonomy["mapping_hash"] = _sha256_json(body)
    write_json(unknown_fixture.taxonomy_identity_path, taxonomy)
    unknown = _read(unknown_fixture)
    assert unknown.status == "accepted"
    assert unknown.industry_filter_usable is False
    assert "membership_taxonomy_code_unsupported:24" in unknown.warnings

    partial_fixture = build_pit_fixture(
        tmp_path / "partial",
        symbols=("2330", "1101"),
        taxonomy_symbols=("2330",),
        security_types={"2330": "common_equity"},
    )
    partial = _read(partial_fixture)
    assert partial.status == "accepted"
    assert partial.industry_filter_usable is False
    assert "membership_taxonomy_partial_denominator" in partial.warnings


def test_v2_reader_blocks_formal_consumption_for_rule_scope_incompatibility(
    tmp_path: Path,
) -> None:
    fixture = build_pit_fixture(tmp_path, symbols=("2330",))
    envelope = load_json(fixture.artifact_path)
    assert isinstance(envelope, dict)
    manifest = envelope["manifest"]
    assert isinstance(manifest, dict)
    manifest.pop("canonical_hash", None)
    manifest["schema_version"] = reader_module.PIT_SPLIT_MANIFEST_SCHEMA_VERSION
    manifest.update(
        {
            "scope_binding_schema_version": reader_module.PIT_TAXONOMY_SCOPE_BINDING_SCHEMA_VERSION,
            "denominator_binding": {"schema_version": "denominator-binding-test.v1"},
            "rule_candidate_binding": {"schema_version": "rule-candidate-binding-test.v1"},
            "scope_diff": {
                "denominator_count": 2,
                "candidate_count": 2,
                "intersection_count": 1,
                "denominator_only_count": 1,
                "rule_only_count": 1,
                "intersection_symbols": ["2330"],
                "intersection_symbols_hash": _sha256_json(["2330"]),
                "denominator_only_symbols": ["1101"],
                "denominator_only_symbols_hash": _sha256_json(["1101"]),
                "rule_only_symbols": ["5371"],
                "rule_only_symbols_hash": _sha256_json(["5371"]),
            },
            "taxonomy_coverage_complete": True,
            "rule_scope_compatible": False,
            "research_only": True,
            "formal_consumer_compatible": False,
        }
    )
    envelope["schema_version"] = reader_module.PIT_SPLIT_SIDECAR_SCHEMA_VERSION
    manifest["canonical_hash"] = _sha256_json(
        {
            "sidecar_schema_version": reader_module.PIT_SPLIT_SIDECAR_SCHEMA_VERSION,
            "manifest": manifest,
        }
    )
    write_json(fixture.artifact_path, envelope)

    result = _read(fixture)

    assert result.status != "accepted"
    assert result.industry_filter_usable is False
    assert result.artifact is not None
    assert result.artifact.artifact_status == "unavailable"
    assert result.artifact.formal_consumer_compatible is False

    # Re-signing a candidate sidecar after changing only its self-declared
    # research/formal flags must not turn the preview schema into an accepted
    # consumer contract.
    manifest["research_only"] = False
    manifest["formal_consumer_compatible"] = True
    manifest.pop("canonical_hash", None)
    manifest["canonical_hash"] = _sha256_json(
        {
            "sidecar_schema_version": reader_module.PIT_SPLIT_SIDECAR_SCHEMA_VERSION,
            "manifest": manifest,
        }
    )
    write_json(fixture.artifact_path, envelope)
    forged = _read(fixture)
    assert forged.status != "accepted"
    assert forged.industry_filter_usable is False
    rows = envelope.get("rows")
    assert isinstance(rows, list)
    try:
        PITSectorMembershipReader([fixture.artifact_path])._parse_sidecar(
            fixture.artifact_path,
            manifest,
            rows,
            decision_at=DECISION_AT,
            sidecar_schema_version=reader_module.PIT_SPLIT_SIDECAR_SCHEMA_VERSION,
        )
    except reader_module.PITMembershipReaderError as error:
        assert str(error) == "PIT split candidate cannot claim formal compatibility"
    else:
        raise AssertionError("re-signed candidate flags must still fail the split reader")


def test_taxonomy_requires_real_source_hash_schema_and_available_at_cutoff(
    tmp_path: Path,
) -> None:
    fake_hash_fixture = build_pit_fixture(tmp_path / "fake-hash", symbols=("2330",))
    fake_hash = load_json(fake_hash_fixture.taxonomy_identity_path)
    assert isinstance(fake_hash, dict)
    fake_hash["source_hash"] = "sha256:" + "0" * 64
    fake_hash_body = dict(fake_hash)
    fake_hash_body.pop("mapping_hash", None)
    fake_hash["mapping_hash"] = _sha256_json(fake_hash_body)
    write_json(fake_hash_fixture.taxonomy_identity_path, fake_hash)
    fake_hash_result = _read(fake_hash_fixture)
    assert fake_hash_result.industry_filter_usable is False
    assert "membership_taxonomy_source_hash_mismatch" in fake_hash_result.warnings

    wrong_source_fixture = build_pit_fixture(
        tmp_path / "wrong-source-schema", symbols=("2330",)
    )
    source = load_json(wrong_source_fixture.taxonomy_source_path)
    assert isinstance(source, dict)
    source["schema_version"] = "wrong-taxonomy-source.v1"
    write_json(wrong_source_fixture.taxonomy_source_path, source)
    wrong_source_result = _read(wrong_source_fixture)
    assert wrong_source_result.industry_filter_usable is False
    assert "membership_taxonomy_source_schema_invalid" in wrong_source_result.warnings

    future_fixture = build_pit_fixture(tmp_path / "future", symbols=("2330",))
    future_at = "2026-08-25T08:31:00+08:00"
    future_source = load_json(future_fixture.taxonomy_source_path)
    future_identity = load_json(future_fixture.taxonomy_identity_path)
    assert isinstance(future_source, dict)
    assert isinstance(future_identity, dict)
    future_source["available_at"] = future_at
    write_json(future_fixture.taxonomy_source_path, future_source)
    future_identity["available_at"] = future_at
    future_identity["source_hash"] = _file_hash(future_fixture.taxonomy_source_path)
    future_identity_body = dict(future_identity)
    future_identity_body.pop("mapping_hash", None)
    future_identity["mapping_hash"] = _sha256_json(future_identity_body)
    write_json(future_fixture.taxonomy_identity_path, future_identity)
    future_result = _read(future_fixture)
    assert future_result.industry_filter_usable is False
    assert "membership_taxonomy_available_at_after_decision" in future_result.warnings


def test_reader_rejects_unknown_taxonomy_classification_version(
    tmp_path: Path,
) -> None:
    fixture = build_pit_fixture(tmp_path, symbols=("2330",))
    source = load_json(fixture.taxonomy_source_path)
    identity = load_json(fixture.taxonomy_identity_path)
    assert isinstance(source, dict)
    assert isinstance(identity, dict)
    source["classification_version"] = "unknown-classification.v99"
    write_json(fixture.taxonomy_source_path, source)
    identity["classification_version"] = source["classification_version"]
    identity["source_hash"] = _file_hash(fixture.taxonomy_source_path)
    identity_body = dict(identity)
    identity_body.pop("mapping_hash", None)
    identity["mapping_hash"] = _sha256_json(identity_body)
    write_json(fixture.taxonomy_identity_path, identity)

    result = _read(fixture)

    assert result.status == "accepted"
    assert result.usable is True
    assert result.industry_filter_usable is False
    assert "membership_taxonomy_classification_version_unsupported" in result.warnings


def test_reader_scopes_non_overlapping_markets_and_fails_true_same_market_conflict(
    tmp_path: Path,
) -> None:
    twse = build_pit_fixture(tmp_path / "twse", symbols=("2330",), clock_suffix="twse")
    # This second artifact is also produced by the official-source and sidecar
    # producers, using the independent TPEx official payload.
    tpex = build_pit_fixture(
        tmp_path / "tpex", symbols=("2317",), market="tpex", clock_suffix="tpex"
    )

    reader = PITSectorMembershipReader(
        [twse.artifact_path, tpex.artifact_path],
        raw_roots=[twse.bundle_root, tpex.bundle_root],
    )
    twse_result = reader.read(
        as_of_date=date(2026, 8, 25),
        decision_at=DECISION_AT,
        market_scope="twse_listed",
    )
    all_markets = reader.read(as_of_date=date(2026, 8, 25), decision_at=DECISION_AT)

    assert twse_result.status == "accepted"
    assert {row.symbol for row in twse_result.rows} == {"2330"}
    assert all_markets.status == "accepted"
    assert {row.market_scope for row in all_markets.rows} == {"twse_listed", "tpex_otc"}

    conflict_a = build_pit_fixture(tmp_path / "conflict-a", symbols=("2330",), clock_suffix="conflict-a")
    conflict_b = build_pit_fixture(tmp_path / "conflict-b", symbols=("1101",), clock_suffix="conflict-b")
    conflict_reader = PITSectorMembershipReader(
        [conflict_a.artifact_path, conflict_b.artifact_path],
        raw_roots=[conflict_a.bundle_root, conflict_b.bundle_root],
    )
    conflict = conflict_reader.read(
        as_of_date=date(2026, 8, 25),
        decision_at=DECISION_AT,
        market_scope="twse_listed",
    )

    assert conflict.status == "unavailable"
    assert "membership_same_date_conflict" in conflict.warnings


def test_reader_handles_machine_candidate_publication_without_promoting_it(
    tmp_path: Path,
) -> None:
    def raw_bytes(value: object) -> bytes:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    publication_dir = tmp_path / "machine-publication"
    publication_dir.mkdir()
    publication = build_machine_pit_publication(
        raw_payloads={
            "twse": raw_bytes(
                [{"公司代號": "2330", "產業別": "24", "出表日期": "20260824"}]
            ),
            "tpex": raw_bytes(
                [
                    {
                        "SecuritiesCompanyCode": "2317",
                        "SecuritiesIndustryCode": "28",
                        "Date": "2026-08-24",
                    }
                ]
            ),
        },
        output_dir=publication_dir,
        captured_at=datetime(2026, 8, 25, 0, 30, tzinfo=timezone.utc),
        now=datetime(2026, 8, 25, 1, 0, tzinfo=timezone.utc),
    )

    result = PITSectorMembershipReader([publication.publication_path]).read(
        as_of_date=date(2026, 8, 25),
        decision_at="2026-08-25T08:30:00+08:00",
    )

    assert result.status == "candidate_only", result.to_dict()
    assert result.rows == ()
    assert result.industry_filter_usable is False
    assert "pit_candidate_only_not_consumable" in result.warnings
