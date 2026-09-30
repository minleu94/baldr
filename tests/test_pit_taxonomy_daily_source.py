from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
from pathlib import Path

import pytest

import data_module.pit_taxonomy_definition_adapter as definition_adapter
import data_module.pit_taxonomy_source_producer as source_producer
from data_module.formal_pit_sector_publisher import (
    publish_daily_pit_taxonomy_sidecar,
)
from data_module.pit_taxonomy_definition_adapter import (
    PIT_TAXONOMY_COMPOSITE_DEFINITION_ADAPTER_VERSION,
    PIT_TAXONOMY_TWSE_B1212_COMPOSITE_SOURCE_KIND,
    OfficialTaxonomyDefinitionError,
    _parse_mapping_from_pdf_text,
    parse_official_classification_definition,
    parse_official_twse_b1212_composite_classification_definition,
)
from data_module.pit_taxonomy_security_adapter import (
    OfficialSecurityTypingError,
    build_security_evidence_map,
    parse_official_isin_security_source,
)
from data_module.pit_taxonomy_source_producer import (
    build_daily_pit_taxonomy_bundle,
    capture_configured_daily_pit_taxonomy_bundle,
    PITTaxonomySourceError,
    PIT_TAXONOMY_SOURCE_CONFIG_SCHEMA_VERSION,
    validate_daily_pit_taxonomy_bundle,
)
from data_module.pit_sector_membership_reader import PITSectorMembershipReader

from tests.pit_test_support import (
    CAPTURE_NOW,
    DECISION_AT,
    _file_hash,
    _sha256_json,
    build_pit_fixture,
    load_json,
    write_json,
)

from scripts.scheduled import run_pit_sector_membership_preopen_capture as capture_runner


def _http(url: str, captured_at: str, content_type: str = "application/json") -> dict[str, object]:
    return {
        "requested_url": url,
        "final_url": url,
        "http_status": 200,
        "content_type": content_type,
        "captured_at": captured_at,
    }


def _security_html(*, tdr_and_foreign_common: bool = False) -> bytes:
    first_type = "TDR" if tdr_and_foreign_common else ""
    second_isin = "KYG123456789" if tdr_and_foreign_common else "TW0002330008"
    return """
    <html><body><table>
      <tr><th>ISIN Code</th><th>Security Code</th><th>Security Name</th>
          <th>Market</th><th>Type of security</th><th>Industrial Group</th>
          <th>CFICode</th><th>Remarks</th></tr>
      <tr><td colspan="8">Stocks</td></tr>
      <tr><td>TW0001101004</td><td>1101</td><td>Alpha</td><td>TWSE</td>
          <td>__FIRST_TYPE__</td><td>Cement</td><td>ESVUFR</td><td></td></tr>
      <tr><td>__SECOND_ISIN__</td><td>2330</td><td>Beta</td><td>TWSE</td>
          <td></td><td>Semiconductor</td><td>ESVUFR</td><td></td></tr>
    </table></body></html>
    """.replace("__FIRST_TYPE__", first_type).replace("__SECOND_ISIN__", second_isin).encode("utf-8")


def _build_bundle(
    tmp_path: Path,
    *,
    license_accepted: bool = True,
    scope_binding: dict[str, object] | None = None,
    expected_symbols: tuple[str, ...] = ("1101", "2330"),
):
    parent = build_pit_fixture(tmp_path / "parent", symbols=("1101", "2330"))
    parent_identity = dict(load_json(parent.universe_identity_path))
    # The legacy fixture predates the explicit hash-symbol projection; the
    # daily producer contract requires the parent full identity to expose it.
    parent_identity["universe_hash_symbols"] = ["1101", "2330"]
    definition_payload = (
        '{"mapping":{"01":"水泥工業","24":"半導體業"}}\n'
    ).encode("utf-8")
    definition = parse_official_classification_definition(
        definition_payload,
        market_scope="twse_listed",
        classification_version="tw-industry-explicit-map.v1",
        source_id="official:twse:industry-definition",
        source_version="2026-08-25",
        effective_from=DECISION_AT.date(),
    )
    result = build_daily_pit_taxonomy_bundle(
        bundle_root=tmp_path / "bundle",
        capture_date=DECISION_AT.date(),
        decision_at=DECISION_AT,
        now=datetime.fromisoformat("2026-08-25T07:55:00+08:00"),
        expected_symbols=expected_symbols,
        universe_hash=str(load_json(parent.universe_identity_path)["universe_hash"]),
        universe_hash_symbols=("1101", "2330"),
        scores_bp=(8000, 8001),
        rank_order=("2330", "1101"),
        clock_id=str(load_json(parent.clock_path)["clock_id"]),
        clock_manifest_hash=str(load_json(parent.clock_path)["manifest_hash"]),
        clock_payload=load_json(parent.clock_path),
        universe_identity_payload=parent_identity,
        universe_symbols_payload=load_json(parent.universe_symbols_path),
        company_raw_payloads={"twse": parent.raw_path.read_bytes()},
        company_http={
            "twse": _http(
                "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
                "2026-08-25T05:00:00+08:00",
            )
        },
        classification_payloads={"twse_listed": definition_payload},
        classification_definitions={"twse_listed": definition},
        classification_http={
            "twse_listed": _http(
                "https://example.invalid/twse-industry-definition",
                "2026-08-25T05:05:00+08:00",
                "application/pdf",
            )
        },
        security_raw_payloads={"twse_listed": _security_html()},
        security_http={
            "twse_listed": _http(
                "https://isin.twse.com.tw/isin/e_single_main.jsp",
                "2026-08-25T05:10:00+08:00",
                "text/html",
            )
        },
        license_scope={
            "status": "owner_accepted_research_scope",
            "formal_acceptance_granted": license_accepted,
            "allowed_use_cases": ["formal_pit_sector_membership"],
            "redistribution_allowed": False,
        },
        scope_binding=scope_binding,
    )
    return result, parent


def _live_capture_inputs(tmp_path: Path) -> tuple[dict[str, object], object, dict[str, tuple[bytes, dict[str, object]]]]:
    parent = build_pit_fixture(tmp_path / "parent", symbols=("1101", "2330"))
    parent_identity = dict(load_json(parent.universe_identity_path))
    parent_identity["universe_hash_symbols"] = ["1101", "2330"]
    definition_payload = '{"mapping":{"01":"水泥工業","24":"半導體業"}}\n'.encode(
        "utf-8"
    )
    security_payload = _security_html()
    definition_url = "https://example.invalid/live-definition"
    security_url = "https://example.invalid/live-security"
    config: dict[str, object] = {
        "schema_version": PIT_TAXONOMY_SOURCE_CONFIG_SCHEMA_VERSION,
        "classification": {
            "twse_listed": {
                "url": definition_url,
                "source_id": "official:twse:industry-definition",
                "source_version": "2026-08-25",
                "classification_version": "tw-industry-explicit-map.v1",
                "effective_from": "2026-08-25",
            }
        },
        "security": {
            "twse_listed": {
                "url": security_url,
            }
        },
        "license_scope": {
            "status": "owner_accepted_research_scope",
            "formal_acceptance_granted": True,
            "acceptance_id": "qa-live-capture-20260825",
            "accepted_by": "qa-owner",
            "decision_at": DECISION_AT.isoformat(),
            "allowed_use_cases": ["formal_pit_sector_membership"],
            "redistribution_allowed": False,
        },
    }
    responses: dict[str, tuple[bytes, dict[str, object]]] = {}
    for url, body in ((definition_url, definition_payload), (security_url, security_payload)):
        responses[url] = (
            body,
            _http(url, "2026-08-25T08:00:00+08:00", "application/json" if url == definition_url else "text/html"),
        )
    inputs: dict[str, object] = {
        "parent_identity": parent_identity,
        "definition_payload": definition_payload,
        "security_payload": security_payload,
        "expected_symbols": ("1101", "2330"),
        "universe_hash": str(parent_identity["universe_hash"]),
        "clock_id": str(load_json(parent.clock_path)["clock_id"]),
        "clock_manifest_hash": str(load_json(parent.clock_path)["manifest_hash"]),
    }
    return config, parent, responses


def _run_live_configured_capture(
    tmp_path: Path,
    *,
    completion_at: str,
    metadata_at: str | None = None,
):
    config, parent, responses = _live_capture_inputs(tmp_path)
    metadata_time = metadata_at or completion_at
    for url, (body, _metadata) in list(responses.items()):
        responses[url] = (
            body,
            _http(
                url,
                metadata_time,
                "application/json" if "definition" in url else "text/html",
            ),
        )
    parent_identity = dict(load_json(parent.universe_identity_path))
    parent_identity["universe_hash_symbols"] = ["1101", "2330"]
    request_started_at = datetime.fromisoformat("2026-08-25T07:55:00+08:00")
    return capture_configured_daily_pit_taxonomy_bundle(
        config=config,
        bundle_root=tmp_path / "live-bundle",
        capture_date=request_started_at.date(),
        decision_at=DECISION_AT,
        now=request_started_at,
        expected_symbols=("1101", "2330"),
        universe_hash=str(parent_identity["universe_hash"]),
        universe_hash_symbols=("1101", "2330"),
        scores_bp=(8000, 8001),
        rank_order=("2330", "1101"),
        clock_id=str(load_json(parent.clock_path)["clock_id"]),
        clock_manifest_hash=str(load_json(parent.clock_path)["manifest_hash"]),
        clock_payload=load_json(parent.clock_path),
        universe_identity_payload=parent_identity,
        company_raw_payloads={"twse": parent.raw_path.read_bytes()},
        company_http={
            "twse": _http(
                "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
                "2026-08-25T05:00:00+08:00",
            )
        },
        universe_symbols_payload=load_json(parent.universe_symbols_path),
        fetch_source=lambda url: responses[url],
        now_provider=lambda: datetime.fromisoformat(completion_at),
    )


def _rule_parent_payload(parent: object) -> dict[str, object]:
    identity = dict(load_json(parent.universe_identity_path))
    identity["universe_hash_symbols"] = ["1101", "2330"]
    clock = load_json(parent.clock_path)
    return {
        "bundle_root": str(parent.bundle_root),
        "identity_path": str(parent.universe_identity_path),
        "symbols_path": str(parent.universe_symbols_path),
        "clock_path": str(parent.clock_path),
        "identity": identity,
        "symbols_payload": load_json(parent.universe_symbols_path),
        "clock": clock,
        "expected_symbols": ("1101", "2330"),
        "universe_hash_symbols": ("1101", "2330"),
        "scores_bp": (8000, 8001),
        "rank_order": ("2330", "1101"),
        "rank_order_source": "fixture.rank_order",
        "universe_hash": str(identity["universe_hash"]),
        "clock_id": str(clock["clock_id"]),
        "clock_manifest_hash": str(clock["manifest_hash"]),
    }


def test_machine_parent_without_rank_order_uses_score_bound_hash_sequence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The v3 machine parent shape has no separate rank_order field."""

    parent = build_pit_fixture(tmp_path / "parent", symbols=("1101", "2330"))
    identity = dict(load_json(parent.universe_identity_path))
    identity["universe_hash_symbols"] = ["1101", "2330"]
    parent.universe_identity_path.write_text(
        json.dumps(identity, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setenv("FORMAL_DAILY_RULE_SOURCE_ROOT", str(parent.bundle_root))

    resolved = capture_runner._find_rule_source_parent(
        parent.bundle_root,
        target_date=DECISION_AT.date(),
    )

    assert resolved["rank_order_source"] == "parent.universe_hash_symbols"
    assert resolved["rank_order"] == resolved["universe_hash_symbols"]
    assert len(resolved["scores_bp"]) == len(resolved["rank_order"])


def test_configured_capture_uses_saved_bytes_and_rejects_mapping_in_config(
    tmp_path: Path,
) -> None:
    parent = build_pit_fixture(tmp_path / "parent", symbols=("1101", "2330"))
    parent_identity = dict(load_json(parent.universe_identity_path))
    parent_identity["universe_hash_symbols"] = ["1101", "2330"]
    definition_payload = '{"mapping":{"01":"水泥工業","24":"半導體業"}}\n'.encode(
        "utf-8"
    )
    definition_path = tmp_path / "twse-definition.raw"
    definition_path.write_bytes(definition_payload)
    security_payload = _security_html()
    security_path = tmp_path / "twse-security.html"
    security_path.write_bytes(security_payload)
    config = {
        "schema_version": PIT_TAXONOMY_SOURCE_CONFIG_SCHEMA_VERSION,
        "classification": {
            "twse_listed": {
                "path": str(definition_path),
                "http": _http(
                    "https://dsp.twse.com.tw/static/industry-definition.pdf",
                    "2026-08-25T05:05:00+08:00",
                    "application/pdf",
                ),
                "source_id": "official:twse:industry-definition",
                "source_version": "2026-08-25",
                "classification_version": "tw-industry-explicit-map.v1",
                "effective_from": "2026-08-25",
            }
        },
        "security": {
            "twse_listed": {
                "path": str(security_path),
                "http": _http(
                    "https://isin.twse.com.tw/isin/e_single_main.jsp",
                    "2026-08-25T05:10:00+08:00",
                    "text/html",
                ),
            }
        },
        "license_scope": {
            "status": "owner_accepted_research_scope",
            "formal_acceptance_granted": True,
            "acceptance_id": "qa-configured-capture-20260825",
            "accepted_by": "qa-owner",
            "decision_at": DECISION_AT.isoformat(),
            "allowed_use_cases": ["formal_pit_sector_membership"],
            "redistribution_allowed": False,
        },
    }
    result = capture_configured_daily_pit_taxonomy_bundle(
        config=config,
        bundle_root=tmp_path / "configured-bundle",
        capture_date=DECISION_AT.date(),
        decision_at=DECISION_AT,
        now=datetime.fromisoformat("2026-08-25T07:55:00+08:00"),
        expected_symbols=("1101", "2330"),
        universe_hash=str(parent_identity["universe_hash"]),
        universe_hash_symbols=("1101", "2330"),
        scores_bp=(8000, 8001),
        rank_order=("2330", "1101"),
        clock_id=str(load_json(parent.clock_path)["clock_id"]),
        clock_manifest_hash=str(load_json(parent.clock_path)["manifest_hash"]),
        clock_payload=load_json(parent.clock_path),
        universe_identity_payload=parent_identity,
        company_raw_payloads={"twse": parent.raw_path.read_bytes()},
        company_http={
            "twse": _http(
                "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
                "2026-08-25T05:00:00+08:00",
            )
        },
        universe_symbols_payload=load_json(parent.universe_symbols_path),
    )
    assert result.status == "preopen_captured"
    assert result.security_type_counts == {"common_equity": 2}
    assert result.market_scope_counts == {"twse_listed": 2}
    config_with_mapping = {
        **config,
        "classification": {
            "twse_listed": {
                **config["classification"]["twse_listed"],
                "mapping": {"01": "手寫名稱"},
            }
        },
    }
    with pytest.raises(PITTaxonomySourceError, match="hand-written mapping"):
        capture_configured_daily_pit_taxonomy_bundle(
            config=config_with_mapping,
            bundle_root=tmp_path / "config-with-mapping",
            capture_date=DECISION_AT.date(),
            decision_at=DECISION_AT,
            now=datetime.fromisoformat("2026-08-25T07:55:00+08:00"),
            expected_symbols=("1101", "2330"),
            universe_hash=str(parent_identity["universe_hash"]),
            universe_hash_symbols=("1101", "2330"),
            scores_bp=(8000, 8001),
            rank_order=("2330", "1101"),
            clock_id=str(load_json(parent.clock_path)["clock_id"]),
            clock_manifest_hash=str(load_json(parent.clock_path)["manifest_hash"]),
            clock_payload=load_json(parent.clock_path),
            universe_identity_payload=parent_identity,
            company_raw_payloads={"twse": parent.raw_path.read_bytes()},
            company_http={
                "twse": _http(
                    "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
                    "2026-08-25T05:00:00+08:00",
                )
            },
            universe_symbols_payload=load_json(parent.universe_symbols_path),
        )


def test_live_configured_capture_uses_completion_clock_after_fetches(
    tmp_path: Path,
) -> None:
    result = _run_live_configured_capture(
        tmp_path,
        completion_at="2026-08-25T08:00:00+08:00",
    )
    bundle = load_json(result.bundle_manifest_path)
    assert bundle["capture_started_at"] == "2026-08-25T07:55:00+08:00"
    assert bundle["captured_at"] == "2026-08-25T08:00:00+08:00"
    raw_manifest = load_json(result.raw_manifest_path)
    assert raw_manifest["captured_at"] == "2026-08-25T08:00:00+08:00"
    assert all(
        entry["available_at"] == "2026-08-25T08:00:00+08:00"
        for entry in raw_manifest["files"]
        if entry["role"] in {"classification_definition", "security_typing"}
    )


def test_live_configured_capture_fails_closed_when_fetch_crosses_cutoff(
    tmp_path: Path,
) -> None:
    with pytest.raises(PITTaxonomySourceError, match="Taipei 08:30"):
        _run_live_configured_capture(
            tmp_path,
            completion_at="2026-08-25T08:31:00+08:00",
        )


def test_live_configured_capture_does_not_rewrite_late_metadata_to_start_time(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        PITTaxonomySourceError,
        match="completion is after capture now|at/after Taipei 08:30",
    ):
        _run_live_configured_capture(
            tmp_path,
            completion_at="2026-08-25T08:29:00+08:00",
            metadata_at="2026-08-25T08:31:00+08:00",
        )


def test_preopen_entrypoint_passes_fetch_completion_clock_to_producer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, parent, responses = _live_capture_inputs(tmp_path)
    config_path = tmp_path / "pit-taxonomy-config.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    parent_payload = _rule_parent_payload(parent)
    monkeypatch.setattr(
        capture_runner,
        "validate_prospective_pit_denominator",
        lambda _path, now=None: {"symbols": ["1101", "2330"]},
    )
    monkeypatch.setattr(
        capture_runner,
        "_find_rule_source_parent",
        lambda *_args, **_kwargs: parent_payload,
    )
    monkeypatch.setattr(
        capture_runner,
        "_load_archived_company_sources",
        lambda _path: (
            {"twse": parent.raw_path.read_bytes()},
            {
                "twse": _http(
                    "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
                    "2026-08-25T05:00:00+08:00",
                )
            },
            {"archive_manifest_path": str(tmp_path / "archive.json")},
        ),
    )
    start = datetime.fromisoformat("2026-08-25T07:55:00+08:00")
    result = capture_runner._capture_taxonomy_for_run(
        publication_root=tmp_path / "publication",
        observed=start,
        denominator={"status": "existing_verified", "path": str(tmp_path / "denominator.json")},
        archive_manifest_path=str(tmp_path / "archive.json"),
        injected_clock=True,
        config_path=config_path,
        fetch_source=lambda url: responses[url],
        now_provider=lambda: datetime.fromisoformat("2026-08-25T08:00:00+08:00"),
    )
    assert result["status"] == "preopen_captured"
    bundle = load_json(Path(str(result["bundle_manifest_path"])))
    assert bundle["capture_started_at"] == start.isoformat()
    assert bundle["captured_at"] == "2026-08-25T08:00:00+08:00"


def test_preopen_entrypoint_blocks_fetch_completion_at_cutoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, parent, responses = _live_capture_inputs(tmp_path)
    config_path = tmp_path / "pit-taxonomy-config.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    parent_payload = _rule_parent_payload(parent)
    monkeypatch.setattr(
        capture_runner,
        "validate_prospective_pit_denominator",
        lambda _path, now=None: {"symbols": ["1101", "2330"]},
    )
    monkeypatch.setattr(
        capture_runner,
        "_find_rule_source_parent",
        lambda *_args, **_kwargs: parent_payload,
    )
    monkeypatch.setattr(
        capture_runner,
        "_load_archived_company_sources",
        lambda _path: (
            {"twse": parent.raw_path.read_bytes()},
            {
                "twse": _http(
                    "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
                    "2026-08-25T05:00:00+08:00",
                )
            },
            {"archive_manifest_path": str(tmp_path / "archive.json")},
        ),
    )
    result = capture_runner._capture_taxonomy_for_run(
        publication_root=tmp_path / "publication",
        observed=datetime.fromisoformat("2026-08-25T07:55:00+08:00"),
        denominator={"status": "existing_verified", "path": str(tmp_path / "denominator.json")},
        archive_manifest_path=str(tmp_path / "archive.json"),
        injected_clock=True,
        config_path=config_path,
        fetch_source=lambda url: responses[url],
        now_provider=lambda: datetime.fromisoformat("2026-08-25T08:31:00+08:00"),
    )
    assert result["status"] == "blocked"
    blockers = result["blockers"]
    assert isinstance(blockers, list)
    assert any("Taipei 08:30" in str(item) for item in blockers)


def test_definition_and_security_negative_rechecks_fail_closed(
    tmp_path: Path,
) -> None:
    raw = '{"mapping":{"01":"水泥工業"}}\n'.encode("utf-8")
    with pytest.raises(OfficialTaxonomyDefinitionError, match="does not derive"):
        parse_official_classification_definition(
            raw,
            market_scope="twse_listed",
            classification_version="tw-industry-explicit-map.v1",
            source_id="official:twse:industry-definition",
            source_version="2026-08-25",
            effective_from=DECISION_AT.date(),
            mapping={"01": "被竄改名稱"},
        )
    records = parse_official_isin_security_source(_security_html())
    with pytest.raises(OfficialSecurityTypingError, match="security_source_missing"):
        build_security_evidence_map(
            records,
            expected_symbols=("1101", "2330", "9999"),
            market_by_symbol={
                "1101": "twse_listed",
                "2330": "twse_listed",
                "9999": "twse_listed",
            },
        )

    future_parent = build_pit_fixture(tmp_path / "future-parent", symbols=("1101", "2330"))
    future_identity = dict(load_json(future_parent.universe_identity_path))
    future_identity["universe_hash_symbols"] = ["1101", "2330"]
    negative_definition_payload = (
        '{"mapping":{"01":"水泥工業","24":"半導體業"}}\n'
    ).encode("utf-8")
    definition = parse_official_classification_definition(
        negative_definition_payload,
        market_scope="twse_listed",
        classification_version="tw-industry-explicit-map.v1",
        source_id="official:twse:industry-definition",
        source_version="2026-08-25",
        effective_from=DECISION_AT.date(),
    )
    with pytest.raises(PITTaxonomySourceError, match="after capture now"):
        build_daily_pit_taxonomy_bundle(
            bundle_root=tmp_path / "future-bundle",
            capture_date=DECISION_AT.date(),
            decision_at=DECISION_AT,
            now=datetime.fromisoformat("2026-08-25T07:55:00+08:00"),
            expected_symbols=("1101", "2330"),
            universe_hash=str(future_identity["universe_hash"]),
            universe_hash_symbols=("1101", "2330"),
            scores_bp=(8000, 8001),
            rank_order=("2330", "1101"),
            clock_id=str(load_json(future_parent.clock_path)["clock_id"]),
            clock_manifest_hash=str(load_json(future_parent.clock_path)["manifest_hash"]),
            clock_payload=load_json(future_parent.clock_path),
            universe_identity_payload=future_identity,
            company_raw_payloads={"twse": future_parent.raw_path.read_bytes()},
            company_http={
                "twse": _http(
                    "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
                    "2026-08-25T05:00:00+08:00",
                )
            },
            classification_payloads={"twse_listed": negative_definition_payload},
            classification_definitions={"twse_listed": definition},
            classification_http={
                "twse_listed": _http(
                    "https://dsp.twse.com.tw/static/industry-definition.pdf",
                    "2026-08-25T08:31:00+08:00",
                    "application/pdf",
                )
            },
            security_raw_payloads={"twse_listed": _security_html()},
            security_http={
                "twse_listed": _http(
                    "https://isin.twse.com.tw/isin/e_single_main.jsp",
                    "2026-08-25T05:10:00+08:00",
                    "text/html",
                )
            },
            license_scope={
                "status": "owner_accepted_research_scope",
                "formal_acceptance_granted": True,
                "acceptance_id": "qa-future-source-20260825",
                "accepted_by": "qa-owner",
                "decision_at": DECISION_AT.isoformat(),
            },
        )


def test_daily_bundle_to_postcutoff_reader_readback(tmp_path: Path) -> None:
    result, _ = _build_bundle(tmp_path)
    assert result.schema_version == source_producer.PIT_TAXONOMY_BUNDLE_SCHEMA_VERSION
    # Keep the legacy v1 result envelope byte/API shape; only split-contract
    # results announce their separate bundle schema.
    assert "schema_version" not in result.to_dict()
    validation = validate_daily_pit_taxonomy_bundle(
        result.bundle_manifest_path,
        decision_at=CAPTURE_NOW,
    )
    assert validation["status"] == "preopen_captured_verified"
    published = publish_daily_pit_taxonomy_sidecar(
        bundle_manifest_path=result.bundle_manifest_path,
        publication_root=tmp_path / "publication",
        decision_at=CAPTURE_NOW,
        now=CAPTURE_NOW,
    )
    assert published["status"] == "formal_source_publication"
    assert published["industry_filter_usable"] is True
    assert published["full_symbol_count"] == 2
    assert published["eligible_symbol_count"] == 2
    assert published["excluded_symbol_count"] == 0


def test_split_scope_binding_rejects_empty_and_reserved_fields_before_writes(
    tmp_path: Path,
) -> None:
    with pytest.raises(PITTaxonomySourceError, match="exactly the approved binding fields"):
        _build_bundle(tmp_path / "empty", scope_binding={})
    assert not (tmp_path / "empty" / "bundle").exists()

    reserved_binding: dict[str, object] = {
        "scope_binding_schema_version": source_producer.PIT_TAXONOMY_SCOPE_BINDING_SCHEMA_VERSION,
        "denominator_binding": {},
        "rule_candidate_binding": {},
        "scope_diff": {},
        "taxonomy_coverage_complete": True,
        "rule_scope_compatible": True,
        "schema_version": "attacker-overridden-schema",
    }
    with pytest.raises(PITTaxonomySourceError, match="exactly the approved binding fields"):
        _build_bundle(tmp_path / "reserved", scope_binding=reserved_binding)
    assert not (tmp_path / "reserved" / "bundle").exists()


def test_legacy_v1_contract_still_rejects_official_universe_mismatch(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        PITTaxonomySourceError,
        match="full universe symbols and universe_hash_symbols must have the same set",
    ):
        _build_bundle(tmp_path, expected_symbols=("1101",))
    assert not (tmp_path / "bundle").exists()


def test_tampered_taxonomy_raw_is_blocked_before_publication(tmp_path: Path) -> None:
    result, _ = _build_bundle(tmp_path)
    raw_path = result.bundle_root / "raw" / "t187ap03_L.raw.json"
    raw_path.write_bytes(raw_path.read_bytes() + b"\n# tampered")
    published = publish_daily_pit_taxonomy_sidecar(
        bundle_manifest_path=result.bundle_manifest_path,
        publication_root=tmp_path / "publication",
        decision_at=CAPTURE_NOW,
        now=CAPTURE_NOW,
    )
    assert published["status"] == "blocked"
    assert published["industry_filter_usable"] is False
    blockers = published["blockers"]
    assert isinstance(blockers, list)
    assert any("raw file hash mismatch" in str(item) for item in blockers)


def test_market_scoped_definition_mapping_keeps_same_code_distinct() -> None:
    twse = parse_official_classification_definition(
        '{"mapping":{"17":"金融保險業"}}\n'.encode("utf-8"),
        market_scope="twse_listed",
        classification_version="tw-industry-explicit-map.v1",
        source_id="official:twse:industry-definition",
        source_version="2026-08-25",
        effective_from=DECISION_AT.date(),
    )
    tpex = parse_official_classification_definition(
        '{"mapping":{"17":"金融業"}}\n'.encode("utf-8"),
        market_scope="tpex_listed",
        classification_version="tw-industry-explicit-map.v1",
        source_id="official:tpex:industry-definition",
        source_version="2026-08-25",
        effective_from=DECISION_AT.date(),
    )
    assert twse.mapping["17"] == "金融保險業"
    assert tpex.mapping["17"] == "金融業"
    assert twse.market_scope != tpex.market_scope


def test_tpex_pdf_table_fixture_is_bounded_and_complete() -> None:
    lines = [
        "目錄 附錄三：產業別代碼 ................................ 85",
        "附錄二：證券編碼規則 03 不是產業名稱",
        "附錄三：產業別代碼",
        "一、上櫃證券產業別代碼",
        "代碼 產業別 代碼 產業別 代碼 產業別 代碼 產業別",
        "02 Food Industry 03 Plastic Industry 04 Textile Fiber 05 Electrical Machinery",
        "06 Electrical Cable 08 Glass Ceramic 10 Steel Industry 11 Rubber Industry",
        "14 Construction 15 Shipping 16 Tourism 17 Finance Industry",
        "20 Other 21 Chemical Industry 22 Biotechnology 23 Oil and Gas",
        "24 Semiconductor 25 Computer Peripheral 26 Optoelectronics 27 Communications",
        "28 Electronic Components 29 Electronic Channel 30 Information Service 31 Other Electronics",
        "頁尾 2026 第 86 頁(V.12.18)",
        "32 Cultural Creative 33 Agricultural Technology 80 Managed Stock 35 Green Energy",
        "36 Digital Cloud 37 Sports Leisure 38 Home Living",
        "附錄四：證券別代碼表 99 不是產業代碼",
        "附錄五：其他 40 數字不可滲入",
    ]
    mapping = _parse_mapping_from_pdf_text("\n".join(lines))
    assert len(mapping) == 31
    assert mapping["02"] == "Food Industry"
    assert mapping["17"] == "Finance Industry"
    assert mapping["32"] == "Cultural Creative"
    assert mapping["80"] == "Managed Stock"
    assert "01" not in mapping
    assert "40" not in mapping
    assert "99" not in mapping


def test_tpex_pdf_table_fixture_rejects_missing_supported_table() -> None:
    with pytest.raises(OfficialTaxonomyDefinitionError, match="supported TPEx"):
        _parse_mapping_from_pdf_text(
            "附錄二：證券編碼規則\n01 Wrong\n附錄四：證券別代碼表"
        )


def test_twse_pdf_table_fixture_is_bounded_and_complete() -> None:
    lines = [
        "目錄 附錄三：證券產業別 ................................ 106",
        "附錄二：證券編碼規則 03 不是產業名稱",
        "附錄三：證券產業別(參照格式一 3.1.3)",
        "（一）中央登錄公債之產業別為其證券代號第一碼及第四碼識別。",
        "（二）一般證券依下表代碼識別",
        "產業別代碼 產業別 產業別代碼 產業別 產業別代碼 產業別 產業別代碼 產業別",
        "01 水泥工業 12 汽車工業 23 油電燃氣業 36 數位雲端",
        "02 食品工業 14 建材營造 24 半導體業 37 運動休閒",
        "03 塑膠工業 15 航運業 25",
        "電腦及週邊",
        "設備業",
        "38 居家生活",
        "04 紡織纖維 16 觀光餐旅 26 光電業",
        "05 電機機械 17 金融保險 27 通信網路業",
        "06 電器電纜 18 貿易百貨 28",
        "電子零組件",
        "業",
        "08 玻璃陶瓷 19 綜合 29 電子通路業",
        "09 造紙工業 20 其他 30 資訊服務業",
        "10 鋼鐵工業 21 化學工業 31 其他電子",
        "11 橡膠工業 22",
        "生技醫療",
        "業",
        "35 綠能環保",
        "臺灣證券交易所 第106頁(B.12.13 版)",
        "附錄四：證券別代碼表 99 不可滲入",
        "附錄五：其他 40 數字不可滲入",
    ]
    mapping = _parse_mapping_from_pdf_text(
        "\n".join(lines),
        market_scope="twse_listed",
    )
    assert len(mapping) == 33
    assert mapping["02"] == "食品工業"
    assert mapping["17"] == "金融保險"
    assert mapping["25"] == "電腦及週邊 設備業"
    assert mapping["38"] == "居家生活"
    assert "40" not in mapping
    assert "99" not in mapping


def test_twse_pdf_table_fixture_rejects_missing_supported_table() -> None:
    with pytest.raises(OfficialTaxonomyDefinitionError, match="supported TWSE"):
        _parse_mapping_from_pdf_text(
            "附錄二：證券編碼規則\n01 Wrong\n附錄三：證券產業別\n"
            "附錄四：證券別代碼表",
            market_scope="twse_listed",
        )


def _stub_pdf_definition_parser(
    monkeypatch: pytest.MonkeyPatch,
    extracted_text: str,
) -> None:
    monkeypatch.setattr(
        definition_adapter,
        "_extract_pdf_text",
        lambda _payload: extracted_text,
    )
    monkeypatch.setattr(
        definition_adapter,
        "_parse_mapping_from_pdf_text",
        lambda _text, *, market_scope: {"01": "水泥工業"},
    )


def _effective_date_evidence(
    *,
    source_id: str = "official:twse:broker-manual",
    source_version: str = "B.12.13-202612",
    effective_from: str = "2026-09-15",
    scope: str = "official_manual_revision_implementation",
) -> dict[str, object]:
    evidence_host = (
        "dsp.tpex.org.tw" if source_id.casefold().startswith("official:tpex:") else "dsp.twse.com.tw"
    )
    return {
        "scope": scope,
        "source_id": source_id,
        "source_version": source_version,
        "effective_from": effective_from,
        "evidence_url": f"https://{evidence_host}/official-manual.pdf",
    }


def _twse_b1212_composite_fixture_payloads() -> dict[str, bytes]:
    base_mapping = {
        "01": "水泥工業",
        "02": "食品工業",
        "03": "塑膠工業",
        "04": "紡織纖維",
        "05": "電機機械",
        "06": "電器電纜",
        "08": "玻璃陶瓷",
        "09": "造紙工業",
        "10": "鋼鐵工業",
        "11": "橡膠工業",
        "12": "汽車工業",
        "14": "建材營造",
        "15": "航運業",
        "16": "觀光事業",
        "17": "金融保險",
        "18": "貿易百貨",
        "19": "綜合",
        "20": "其他",
        "21": "化學工業",
        "22": "生技醫療業",
        "23": "油電燃氣業",
        "24": "半導體業",
        "25": "電腦及週邊設備業",
        "26": "光電業",
        "27": "通信網路業",
        "28": "電子零組件業",
        "29": "電子通路業",
        "30": "資訊服務業",
        "31": "其他電子業",
    }
    table_rows = []
    items = list(base_mapping.items())
    for index in range(0, len(items), 4):
        table_rows.append(" ".join(f"{code} {name}" for code, name in items[index:index + 4]))
    base_text = "\n".join(
        [
            "版本 B.12.00",
            "附錄三：證券產業別",
            "產業別代碼 產業別 產業別代碼 產業別 產業別代碼 產業別 產業別代碼 產業別",
            *table_rows,
            "附錄四：證券別代碼表",
        ]
    )
    history_text = "\n".join(
        [
            "版本 B.12.13",
            "版本更新紀錄",
            "B.12.00 107/10 修改 109/03 實施 逐筆交易欄位調整",
            "B12.01 109/04 修改 109/10 實施 新增格式二十二、二十三",
            "B12.02 110/02 修改 110/06 實施 創新板格式調整",
            "B12.03 111/03 修改 111/04 實施 修改附錄二證券編碼規則",
            "B12.04 111/05 修改 111/06 實施 修改附錄二證券編碼規則",
            "B12.05 111/02 修改 111/06 實施 新增格式二十四、二十五",
            "B12.06 111/10 修改 111/11 實施 修改附錄二證券編碼規則",
            "B12.07 112/03 修改 112/07 實施 修改附錄三：證券產業別，"
            "觀光事業 觀光餐旅 綠能環保 數位雲端 運動休閒 居家生活",
            "B12.08 113/03 修改 113/07 實施 移除格式三資料",
            "B12.09 113/09 修改 113/11 實施 修改附錄二 ETF 編碼",
            "B12.10 113/10 修改 113/11 實施 修改附錄二 ETF 編碼起始區間",
            "B12.11 114/01 修改 114/03 實施 修改附錄二 ETF 證券類別",
            "B12.12 115/04 修改 115/04 實施 調整格式六、格式十七、格式二十、"
            "格式二十三、格式二十四 序號 2.5 傳輸序號欄位規則",
            "B12.13 115/05 修改 115/08 修改 115/12 實施",
        ]
    )
    change_text = """
    <html><body>
      <p>本公司將於112年7月3日新增四項產業類別。</p>
      <p>(1) 綠能環保(產業別代碼:35)。</p>
      <p>(2) 數位雲端(產業別代碼:36)。</p>
      <p>(3) 運動休閒(產業別代碼:37)。</p>
      <p>(4) 居家生活(產業別代碼:38)。</p>
      <p>另將「觀光事業」名稱調整為「觀光餐旅」(產業別代碼:16)。</p>
    </body></html>
    """
    final_names = list(base_mapping.values())
    final_names[final_names.index("觀光事業")] = "觀光餐旅"
    final_names.extend(("綠能環保", "數位雲端", "運動休閒", "居家生活"))
    regulation_text = (
        "<html><body><pre>上市公司產業類別為"
        + "、".join(final_names)
        + "等三十三種產業類別</pre></body></html>"
    )
    return {
        "base_definition": b"%PDF-BASE",
        "change_notice": change_text.encode("utf-8"),
        "revision_history": b"%PDF-HISTORY",
        "current_regulation": regulation_text.encode("utf-8"),
        "base_text": base_text.encode("utf-8"),
        "history_text": history_text.encode("utf-8"),
    }


def _composite_evidence() -> dict[str, object]:
    return {
        "scope": "official_manual_revision_implementation",
        "source_id": "official:twse:broker-manual:O-126-A10",
        "source_version": "B.12.12-rederived",
        "effective_from": "2026-05-01",
        "evidence_url": "https://dsp.twse.com.tw/brokerManual/list",
    }


def _stub_twse_b1212_pdf_text(
    monkeypatch: pytest.MonkeyPatch,
    payloads: dict[str, bytes],
) -> None:
    texts = {
        payloads["base_definition"]: payloads["base_text"].decode("utf-8"),
        payloads["revision_history"]: payloads["history_text"].decode("utf-8"),
    }
    monkeypatch.setattr(definition_adapter, "_extract_pdf_text", lambda raw: texts[raw])


def test_twse_b1212_composite_rederives_mapping_from_four_raw_components(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads = _twse_b1212_composite_fixture_payloads()
    _stub_twse_b1212_pdf_text(monkeypatch, payloads)
    definition = parse_official_twse_b1212_composite_classification_definition(
        base_raw_payload=payloads["base_definition"],
        change_raw_payload=payloads["change_notice"],
        revision_history_raw_payload=payloads["revision_history"],
        current_regulation_raw_payload=payloads["current_regulation"],
        classification_version="twse-industry-definition.v1",
        source_id="official:twse:broker-manual:O-126-A10",
        source_version="B.12.12-rederived",
        effective_from=date(2026, 5, 1),
        effective_date_basis="official_manual_implementation_record",
        effective_date_evidence=_composite_evidence(),
    )
    assert definition.parser_version == PIT_TAXONOMY_COMPOSITE_DEFINITION_ADAPTER_VERSION
    assert definition.source_kind == PIT_TAXONOMY_TWSE_B1212_COMPOSITE_SOURCE_KIND
    assert len(definition.mapping) == 33
    assert definition.mapping["16"] == "觀光餐旅"
    assert definition.mapping["25"] == "電腦及週邊設備業"
    assert definition.mapping["38"] == "居家生活"
    assert definition.source_lineage is not None
    assert definition.source_lineage["revision_history"]["b1212_appendix3_change_proven"] is False

    tampered_change = payloads["change_notice"].replace("綠能環保".encode("utf-8"), "綠能能源".encode("utf-8"))
    with pytest.raises(OfficialTaxonomyDefinitionError, match="current regulation"):
        parse_official_twse_b1212_composite_classification_definition(
            base_raw_payload=payloads["base_definition"],
            change_raw_payload=tampered_change,
            revision_history_raw_payload=payloads["revision_history"],
            current_regulation_raw_payload=payloads["current_regulation"],
            classification_version="twse-industry-definition.v1",
            source_id="official:twse:broker-manual:O-126-A10",
            source_version="B.12.12-rederived",
            effective_from=date(2026, 5, 1),
            effective_date_basis="official_manual_implementation_record",
            effective_date_evidence=_composite_evidence(),
        )


def test_twse_b1212_composite_rejects_industry_change_in_intermediate_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads = _twse_b1212_composite_fixture_payloads()
    bad_history = payloads["history_text"].replace(
        "B12.10 113/10 修改 113/11 實施 修改附錄二 ETF 編碼起始區間".encode("utf-8"),
        "B12.10 113/10 修改 113/11 實施 修改附錄三產業別代碼".encode("utf-8"),
    )
    payloads["revision_history"] = b"%PDF-HISTORY-BAD"
    payloads["history_text"] = bad_history
    _stub_twse_b1212_pdf_text(monkeypatch, payloads)
    with pytest.raises(OfficialTaxonomyDefinitionError, match="unsupported industry mapping change in B12.10"):
        parse_official_twse_b1212_composite_classification_definition(
            base_raw_payload=payloads["base_definition"],
            change_raw_payload=payloads["change_notice"],
            revision_history_raw_payload=payloads["revision_history"],
            current_regulation_raw_payload=payloads["current_regulation"],
            classification_version="twse-industry-definition.v1",
            source_id="official:twse:broker-manual:O-126-A10",
            source_version="B.12.12-rederived",
            effective_from=date(2026, 5, 1),
            effective_date_basis="official_manual_implementation_record",
            effective_date_evidence=_composite_evidence(),
        )


def test_configured_composite_capture_custodies_component_raw_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads = _twse_b1212_composite_fixture_payloads()
    _stub_twse_b1212_pdf_text(monkeypatch, payloads)
    parent = build_pit_fixture(tmp_path / "parent", symbols=("1101", "2330"))
    parent_identity = dict(load_json(parent.universe_identity_path))
    parent_identity["universe_hash_symbols"] = ["1101", "2330"]
    component_urls = {
        "base_definition": "https://wwwc.twse.com.tw/staticFiles/product/broker/base.pdf",
        "change_notice": "https://eshop.twse.com.tw/zh/news/detail/change",
        "revision_history": "https://dsp.twse.com.tw/public/static/downloads/future.pdf",
        "current_regulation": "https://twse-regulation.twse.com.tw/tw/law/current",
    }
    components: dict[str, object] = {}
    for index, component_name in enumerate(
        ("base_definition", "change_notice", "revision_history", "current_regulation")
    ):
        component_path = tmp_path / f"{component_name}.raw"
        component_path.write_bytes(payloads[component_name])
        components[component_name] = {
            "path": str(component_path),
            "http": _http(
                component_urls[component_name],
                f"2026-08-25T05:0{index}:00+08:00",
                "application/pdf" if payloads[component_name].startswith(b"%PDF") else "text/html",
            ),
        }
    components["base_definition"]["http"]["http_date"] = (
        "Tue, 25 Aug 2026 05:00:00 GMT"
    )
    components["base_definition"]["http"]["http_last_modified"] = (
        "Mon, 24 Aug 2026 20:00:00 GMT"
    )
    security_path = tmp_path / "security.html"
    security_path.write_bytes(_security_html())
    config = {
        "schema_version": PIT_TAXONOMY_SOURCE_CONFIG_SCHEMA_VERSION,
        "classification": {
            "twse_listed": {
                "source_kind": PIT_TAXONOMY_TWSE_B1212_COMPOSITE_SOURCE_KIND,
                "source_url": "https://dsp.twse.com.tw/brokerManual/list",
                "source_id": "official:twse:broker-manual:O-126-A10",
                "source_version": "B.12.12-rederived",
                "classification_version": "twse-industry-definition.v1",
                "effective_from": "2026-05-01",
                "effective_date_basis": "official_manual_implementation_record",
                "effective_date_evidence": _composite_evidence(),
                "components": components,
            }
        },
        "security": {
            "twse_listed": {
                "path": str(security_path),
                "http": _http(
                    "https://isin.twse.com.tw/isin/e_single_main.jsp",
                    "2026-08-25T05:10:00+08:00",
                    "text/html",
                ),
            }
        },
        "license_scope": {
            "status": "owner_accepted_research_scope",
            "formal_acceptance_granted": True,
            "acceptance_id": "qa-composite-capture-20260825",
            "accepted_by": "qa-owner",
            "decision_at": DECISION_AT.isoformat(),
            "allowed_use_cases": ["formal_pit_sector_membership"],
            "redistribution_allowed": False,
        },
    }
    result = capture_configured_daily_pit_taxonomy_bundle(
        config=config,
        bundle_root=tmp_path / "composite-bundle",
        capture_date=DECISION_AT.date(),
        decision_at=DECISION_AT,
        now=datetime.fromisoformat("2026-08-25T07:55:00+08:00"),
        expected_symbols=("1101", "2330"),
        universe_hash=str(parent_identity["universe_hash"]),
        universe_hash_symbols=("1101", "2330"),
        scores_bp=(8000, 8001),
        rank_order=("2330", "1101"),
        clock_id=str(load_json(parent.clock_path)["clock_id"]),
        clock_manifest_hash=str(load_json(parent.clock_path)["manifest_hash"]),
        clock_payload=load_json(parent.clock_path),
        universe_identity_payload=parent_identity,
        company_raw_payloads={"twse": parent.raw_path.read_bytes()},
        company_http={
            "twse": _http(
                "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
                "2026-08-25T05:00:00+08:00",
            )
        },
        universe_symbols_payload=load_json(parent.universe_symbols_path),
    )
    raw_manifest = load_json(result.raw_manifest_path)
    component_entries = [
        entry
        for entry in raw_manifest["files"]
        if entry["role"] == "classification_definition_component"
    ]
    assert {entry["path"] for entry in component_entries} == {
        "raw/twse_listed_industry_definition_change_notice.html",
        "raw/twse_listed_industry_definition_revision_history.pdf",
        "raw/twse_listed_industry_definition_current_regulation.html",
    }
    classification_entry = next(
        entry
        for entry in raw_manifest["files"]
        if entry["role"] == "classification_definition"
    )
    assert classification_entry["source_kind"] == PIT_TAXONOMY_TWSE_B1212_COMPOSITE_SOURCE_KIND
    assert classification_entry["source_lineage"]["base_revision"] == "B.12.00"
    assert classification_entry["http"]["requested_url"] == component_urls["base_definition"]
    assert classification_entry["http"]["final_url"] == component_urls["base_definition"]
    assert classification_entry["http"]["content_type"] == "application/pdf"
    assert classification_entry["http"]["captured_at"] == "2026-08-25T05:00:00+08:00"
    assert classification_entry["http"]["http_date"] == "Tue, 25 Aug 2026 05:00:00 GMT"
    assert classification_entry["http"]["http_last_modified"] == "Mon, 24 Aug 2026 20:00:00 GMT"
    assert classification_entry["derived_metadata"]["metadata_kind"] == "derived_composite"
    assert "http_status" not in classification_entry["derived_metadata"]



    assert (
        classification_entry["source_lineage"]["components"]["base_definition"]["sha256"]
        == classification_entry["source_file_hash"]
    )

    publication = publish_daily_pit_taxonomy_sidecar(
        bundle_manifest_path=result.bundle_manifest_path,
        publication_root=tmp_path / "published",
        decision_at=DECISION_AT,
        now=datetime.fromisoformat("2026-08-25T09:00:00+08:00"),
    )
    assert publication["reader_status"] == "accepted", publication
    assert publication["industry_filter_usable"] is True, publication["blockers"]

    # Recompute every outer binding after changing only the primary base HTTP
    # capture metadata.  The reader must still reject the composite because
    # the real component capture is after the preserved derived completion.
    sidecar_path = Path(str(publication["sidecar_path"]))
    target_root = sidecar_path.parent.parent
    raw_manifest_path = Path(str(publication["raw_manifest_path"]))
    taxonomy_source_path = Path(str(publication["taxonomy_source_path"]))
    taxonomy_identity_path = Path(str(publication["taxonomy_identity_path"]))
    tampered_at = "2026-08-25T08:31:00+08:00"

    tampered_raw_manifest = load_json(raw_manifest_path)
    assert isinstance(tampered_raw_manifest, dict)
    tampered_primary = next(
        entry
        for entry in tampered_raw_manifest["files"]
        if entry["role"] == "classification_definition"
    )
    assert isinstance(tampered_primary, dict)
    tampered_primary_http = tampered_primary["http"]
    assert isinstance(tampered_primary_http, dict)
    tampered_primary_http["captured_at"] = tampered_at
    raw_manifest_body = dict(tampered_raw_manifest)
    raw_manifest_body.pop("manifest_hash", None)
    tampered_raw_manifest["manifest_hash"] = _sha256_json(raw_manifest_body)
    write_json(raw_manifest_path, tampered_raw_manifest)
    tampered_raw_manifest_hash = _file_hash(raw_manifest_path)

    tampered_source = load_json(taxonomy_source_path)
    assert isinstance(tampered_source, dict)
    tampered_source_classification = tampered_source["classification_sources_by_market"]
    assert isinstance(tampered_source_classification, dict)
    tampered_source_market = tampered_source_classification["twse_listed"]
    assert isinstance(tampered_source_market, dict)
    tampered_source_http = tampered_source_market["http"]
    assert isinstance(tampered_source_http, dict)
    tampered_source_http["captured_at"] = tampered_at
    tampered_source["raw_manifest_hash"] = tampered_raw_manifest_hash
    write_json(taxonomy_source_path, tampered_source)
    tampered_source_hash = _file_hash(taxonomy_source_path)

    tampered_identity = load_json(taxonomy_identity_path)
    assert isinstance(tampered_identity, dict)
    tampered_identity_classification = tampered_identity[
        "classification_sources_by_market"
    ]
    assert isinstance(tampered_identity_classification, dict)
    tampered_identity_market = tampered_identity_classification["twse_listed"]
    assert isinstance(tampered_identity_market, dict)
    tampered_identity_http = tampered_identity_market["http"]
    assert isinstance(tampered_identity_http, dict)
    tampered_identity_http["captured_at"] = tampered_at
    tampered_identity["raw_manifest_hash"] = tampered_raw_manifest_hash
    tampered_identity["source_hash"] = tampered_source_hash
    identity_body = dict(tampered_identity)
    identity_body.pop("mapping_hash", None)
    tampered_identity["mapping_hash"] = _sha256_json(identity_body)
    write_json(taxonomy_identity_path, tampered_identity)
    tampered_identity_hash = _file_hash(taxonomy_identity_path)

    tampered_bundle_path = target_root / "bundle_manifest.json"
    tampered_bundle = load_json(tampered_bundle_path)
    assert isinstance(tampered_bundle, dict)
    tampered_bundle["raw_manifest_hash"] = tampered_raw_manifest_hash
    tampered_bundle["taxonomy_source_hash"] = tampered_source_hash
    tampered_bundle["taxonomy_identity_hash"] = tampered_identity_hash
    bundle_body = dict(tampered_bundle)
    bundle_body.pop("bundle_hash", None)
    tampered_bundle["bundle_hash"] = _sha256_json(bundle_body)
    write_json(tampered_bundle_path, tampered_bundle)

    tampered_sidecar = load_json(sidecar_path)
    assert isinstance(tampered_sidecar, dict)
    tampered_manifest = tampered_sidecar["manifest"]
    assert isinstance(tampered_manifest, dict)
    tampered_manifest["taxonomy_raw_manifest_hash"] = tampered_raw_manifest_hash
    tampered_manifest["taxonomy_source_hash"] = tampered_source_hash
    tampered_manifest["taxonomy_identity_hash"] = tampered_identity_hash
    tampered_manifest["taxonomy_bundle_hash"] = tampered_bundle["bundle_hash"]
    sidecar_manifest_body = dict(tampered_manifest)
    sidecar_manifest_body.pop("canonical_hash", None)
    tampered_manifest["canonical_hash"] = _sha256_json(
        {
            "sidecar_schema_version": tampered_sidecar["schema_version"],
            "manifest": sidecar_manifest_body,
        }
    )
    write_json(sidecar_path, tampered_sidecar)

    receipt_path = Path(str(publication["receipt_path"]))
    tampered_receipt = load_json(receipt_path)
    assert isinstance(tampered_receipt, dict)
    tampered_receipt["sidecar_file_hash"] = _file_hash(sidecar_path)
    receipt_body = dict(tampered_receipt)
    receipt_body.pop("receipt_hash", None)
    tampered_receipt["receipt_hash"] = _sha256_json(receipt_body)
    write_json(receipt_path, tampered_receipt)

    tampered_readback = PITSectorMembershipReader(
        [sidecar_path],
        raw_roots=[target_root],
        universe_symbols_paths=[target_root / "metadata" / "universe_symbols.json"],
        universe_identity_paths=[target_root / "metadata" / "universe_identity.json"],
        clock_manifest_paths=[target_root / "clock" / "manifest.json"],
        taxonomy_identity_paths=[taxonomy_identity_path],
    ).read(as_of_date=DECISION_AT.date(), decision_at=DECISION_AT)
    assert tampered_readback.industry_filter_usable is False
    assert any(
        "captured_after_derived" in warning
        or "derived_completion_mismatch" in warning
        for warning in tampered_readback.warnings
    ), tampered_readback.warnings


def _capture_attempt_fixture(
    tmp_path: Path,
    *,
    attempt_id: str = "0123456789abcdef0123456789abcdef",
    status: int = 200,
):
    publication_root = tmp_path / "publication"
    publication_root.mkdir(parents=True, exist_ok=True)
    capture_date = date(2026, 8, 25)
    started_at = datetime.fromisoformat("2026-08-25T07:55:00+08:00")
    custody_at = datetime.fromisoformat("2026-08-25T08:00:00+08:00")
    scope_binding: dict[str, object] = {
        "scope_binding_schema_version": source_producer.PIT_TAXONOMY_SCOPE_BINDING_SCHEMA_VERSION,
        "denominator_binding": {"fixture": "denominator"},
        "rule_candidate_binding": {"fixture": "rule"},
        "scope_diff": {"fixture": "diff"},
        "taxonomy_coverage_complete": True,
        "rule_scope_compatible": False,
    }
    attempt = source_producer._PITTaxonomyCaptureAttempt(
        publication_root=publication_root,
        capture_date=capture_date,
        attempt_id=attempt_id,
        started_at=started_at,
        scope_binding=scope_binding,
        universe_hash="sha256:" + "1" * 64,
        clock_id="clock:fixture",
        clock_manifest_hash="sha256:" + "2" * 64,
        source_config_hash="sha256:" + "3" * 64,
        planned_sources=[{"source_name": "security:twse_listed", "mode": "url"}],
        custody_now=lambda: custody_at,
    )
    metadata = _http(
        "https://isin.twse.com.tw/isin/e_single_main.jsp",
        "2026-08-25T08:00:00+08:00",
        "text/html",
    )
    metadata["http_status"] = status
    attempt.record_component(
        "security:twse_listed", b"official response body", metadata, fetched=True
    )
    return publication_root, capture_date, started_at, scope_binding, attempt


def test_split_capture_attempt_success_binds_and_revalidates_receipt(
    tmp_path: Path,
) -> None:
    publication_root, capture_date, started_at, scope_binding, attempt = (
        _capture_attempt_fixture(tmp_path)
    )
    binding = attempt.seal_inputs()
    bundle_path = (
        publication_root
        / "pit_taxonomy_preopen_split_v2"
        / capture_date.isoformat()
        / "bundle_manifest.json"
    )
    bundle_path.parent.mkdir(parents=True)
    bundle_hash = "sha256:" + "4" * 64
    bundle_path.write_text(json.dumps({"bundle_hash": bundle_hash}), encoding="utf-8")
    attempt.finish_success(bundle_manifest_path=bundle_path)

    verified = source_producer._verify_capture_attempt_binding(
        binding,
        publication_root=publication_root,
        capture_date=capture_date,
        capture_started_at=started_at,
        decision_at=DECISION_AT,
        universe_hash="sha256:" + "1" * 64,
        clock_id="clock:fixture",
        clock_manifest_hash="sha256:" + "2" * 64,
        scope_binding=scope_binding,
        expected_bundle_hash=bundle_hash,
        require_success=True,
    )
    assert verified["capture_attempt_verified"] is True
    assert verified["capture_attempt_id"] == attempt.attempt_id
    readback = source_producer.read_pit_taxonomy_capture_attempt(
        attempt.root, verify_complete=True
    )
    assert readback["status"] == "success"
    assert readback["component_count"] == 1


@pytest.mark.parametrize("mutated_file", ["raw", "metadata"])
def test_failed_attempt_body_is_readable_and_component_mutation_is_rejected(
    tmp_path: Path,
    mutated_file: str,
) -> None:
    _publication, _capture_date, _started, _scope, attempt = _capture_attempt_fixture(
        tmp_path, attempt_id=("a" if mutated_file == "raw" else "b") * 32, status=503
    )
    error = PITTaxonomySourceError("HTTP status intentionally rejected")
    attempt.finish_failure(error)
    readback = source_producer.read_pit_taxonomy_capture_attempt(attempt.root)
    assert readback["status"] == "failed"
    components = readback["components"]
    assert isinstance(components, list) and len(components) == 1
    component = components[0]
    assert isinstance(component, dict)
    raw_path = attempt.root / str(component["raw_path"])
    assert raw_path.read_bytes() == b"official response body"
    target = (
        raw_path
        if mutated_file == "raw"
        else attempt.root / str(component["metadata_path"])
    )
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(PITTaxonomySourceError, match="pinned|hash"):
        source_producer.read_pit_taxonomy_capture_attempt(attempt.root)


def test_split_capture_attempt_partial_is_untrusted_and_pins_raw_hash(
    tmp_path: Path,
) -> None:
    _publication, _capture_date, _started, _scope, attempt = _capture_attempt_fixture(
        tmp_path, attempt_id="c" * 32
    )
    readback = source_producer.read_pit_taxonomy_capture_attempt(attempt.root)
    assert readback["status"] == "partial_untrusted"
    components = readback["components"]
    assert isinstance(components, list) and len(components) == 1
    raw_path = attempt.root / str(components[0]["raw_path"])
    raw_path.write_bytes(b"mutated partial body")
    with pytest.raises(PITTaxonomySourceError, match="pinned component metadata"):
        source_producer.read_pit_taxonomy_capture_attempt(attempt.root)


def test_failed_after_seal_attempt_pins_and_rejects_receipt_mutation(
    tmp_path: Path,
) -> None:
    _publication, _capture_date, _started, _scope, attempt = _capture_attempt_fixture(
        tmp_path, attempt_id="9" * 32
    )
    attempt.seal_inputs()
    attempt.finish_failure(PITTaxonomySourceError("post-capture validation failed"))
    receipt_path = attempt.root / "capture_receipt.json"
    receipt_path.write_bytes(receipt_path.read_bytes() + b" ")
    with pytest.raises(PITTaxonomySourceError, match="terminal receipt hash"):
        source_producer.read_pit_taxonomy_capture_attempt(attempt.root)


def test_split_configured_capture_saves_non_200_body_before_status_rejection(
    tmp_path: Path,
) -> None:
    publication_root = tmp_path / "publication"
    capture_date = DECISION_AT.date()
    bundle_root = (
        publication_root
        / "pit_taxonomy_preopen_split_v2"
        / capture_date.isoformat()
    )
    scope_binding: dict[str, object] = {
        "scope_binding_schema_version": source_producer.PIT_TAXONOMY_SCOPE_BINDING_SCHEMA_VERSION,
        "denominator_binding": {},
        "rule_candidate_binding": {},
        "scope_diff": {},
        "taxonomy_coverage_complete": True,
        "rule_scope_compatible": False,
    }
    url = "https://example.invalid/security"
    response_metadata = _http(url, "2026-08-25T08:00:00+08:00", "text/html")
    response_metadata["http_status"] = 503
    config: dict[str, object] = {
        "classification": {},
        "security": {"twse_listed": {"url": url}},
    }
    with pytest.raises(PITTaxonomySourceError, match="http_status must be 200") as captured:
        capture_configured_daily_pit_taxonomy_bundle(
            config=config,
            bundle_root=bundle_root,
            capture_date=capture_date,
            decision_at=DECISION_AT,
            now=datetime.fromisoformat("2026-08-25T07:55:00+08:00"),
            expected_symbols=("1101",),
            universe_hash="sha256:" + "1" * 64,
            universe_hash_symbols=("1101",),
            scores_bp=(8000,),
            rank_order=("1101",),
            clock_id="clock:fixture",
            clock_manifest_hash="sha256:" + "2" * 64,
            clock_payload={},
            universe_identity_payload={},
            company_raw_payloads={},
            company_http={},
            scope_binding=scope_binding,
            fetch_source=lambda _url: (b"bounded failure body", response_metadata),
            capture_attempt_id="e" * 32,
            now_provider=lambda: datetime.fromisoformat("2026-08-25T08:00:00+08:00"),
        )
    attempt_root = Path(getattr(captured.value, "capture_attempt")["path"])
    readback = source_producer.read_pit_taxonomy_capture_attempt(attempt_root)
    assert readback["status"] == "failed"
    components = readback["components"]
    assert isinstance(components, list) and len(components) == 1
    component = components[0]
    assert isinstance(component, dict)
    assert (attempt_root / str(component["raw_path"])).read_bytes() == b"bounded failure body"
    assert component["http_metadata"]["http_status"] == 503


def test_split_capture_attempt_rejects_aggregate_raw_byte_overflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publication_root = tmp_path / "publication"
    publication_root.mkdir()
    monkeypatch.setattr(
        source_producer, "PIT_TAXONOMY_CAPTURE_MAX_TOTAL_RAW_BYTES", 3
    )
    custody_at = datetime.fromisoformat("2026-08-25T08:00:00+08:00")
    attempt = source_producer._PITTaxonomyCaptureAttempt(
        publication_root=publication_root,
        capture_date=DECISION_AT.date(),
        attempt_id="f" * 32,
        started_at=datetime.fromisoformat("2026-08-25T07:55:00+08:00"),
        scope_binding={
            "scope_binding_schema_version": source_producer.PIT_TAXONOMY_SCOPE_BINDING_SCHEMA_VERSION,
            "denominator_binding": {},
            "rule_candidate_binding": {},
            "scope_diff": {},
            "taxonomy_coverage_complete": True,
            "rule_scope_compatible": False,
        },
        universe_hash="sha256:" + "1" * 64,
        clock_id="clock:fixture",
        clock_manifest_hash="sha256:" + "2" * 64,
        source_config_hash="sha256:" + "3" * 64,
        planned_sources=[
            {"source_name": "security:a", "mode": "url"},
            {"source_name": "security:b", "mode": "url"},
        ],
        custody_now=lambda: custody_at,
    )
    attempt.record_component(
        "security:a",
        b"ab",
        _http("https://example.invalid/a", "2026-08-25T08:00:00+08:00"),
        fetched=True,
    )
    with pytest.raises(PITTaxonomySourceError, match="aggregate raw-byte limit"):
        attempt.record_component(
            "security:b",
            b"cd",
            _http("https://example.invalid/b", "2026-08-25T08:00:00+08:00"),
            fetched=True,
        )
    attempt.finish_failure(PITTaxonomySourceError("aggregate bound reached"))
    readback = source_producer.read_pit_taxonomy_capture_attempt(attempt.root)
    assert readback["status"] == "failed"
    assert readback["component_count"] == 1
    rejected = readback.get("rejected_components")
    assert isinstance(rejected, list) and rejected[0]["source_name"] == "security:b"
    assert rejected[0]["full_body_saved"] is False


def test_split_capture_attempt_pins_bounded_oversize_diagnostic_without_claiming_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publication_root = tmp_path / "publication"
    publication_root.mkdir()
    monkeypatch.setattr(source_producer, "PIT_TAXONOMY_MAX_SOURCE_BYTES", 3)
    custody_at = datetime.fromisoformat("2026-08-25T08:00:00+08:00")
    attempt = source_producer._PITTaxonomyCaptureAttempt(
        publication_root=publication_root,
        capture_date=DECISION_AT.date(),
        attempt_id="a" * 32,
        started_at=datetime.fromisoformat("2026-08-25T07:55:00+08:00"),
        scope_binding={
            "scope_binding_schema_version": source_producer.PIT_TAXONOMY_SCOPE_BINDING_SCHEMA_VERSION,
            "denominator_binding": {},
            "rule_candidate_binding": {},
            "scope_diff": {},
            "taxonomy_coverage_complete": True,
            "rule_scope_compatible": False,
        },
        universe_hash="sha256:" + "1" * 64,
        clock_id="clock:fixture",
        clock_manifest_hash="sha256:" + "2" * 64,
        source_config_hash="sha256:" + "3" * 64,
        planned_sources=[{"source_name": "security:oversize", "mode": "url"}],
        custody_now=lambda: custody_at,
    )
    response_metadata = _http(
        "https://example.invalid/oversize", "2026-08-25T08:00:00+08:00"
    )
    response_metadata.update({"body_truncated": True, "body_bytes_seen": 4})
    with pytest.raises(PITTaxonomySourceError, match="per-source byte limit"):
        attempt.record_component(
            "security:oversize", b"abcd", response_metadata, fetched=True
        )
    attempt.finish_failure(PITTaxonomySourceError("oversize response"))
    readback = source_producer.read_pit_taxonomy_capture_attempt(attempt.root)
    assert readback["component_count"] == 0
    rejected = readback["rejected_components"]
    assert rejected == [
        {
            "source_name": "security:oversize",
            "reason": "per_source_byte_limit",
            "bytes_seen": 4,
            "truncated": True,
            "full_body_saved": False,
        }
    ]


def test_split_capture_attempt_rejects_oversize_terminal_result(
    tmp_path: Path,
) -> None:
    _publication, _capture_date, _started, _scope, attempt = _capture_attempt_fixture(
        tmp_path
    )
    attempt.finish_failure(PITTaxonomySourceError("fixture terminal"))
    attempt.result_path.write_bytes(b" " * (1024 * 1024 + 1))
    with pytest.raises(PITTaxonomySourceError, match="capture attempt result proof file custody failed"):
        source_producer.read_pit_taxonomy_capture_attempt(attempt.root)


def test_split_saved_active_source_bounds_before_readback_or_custody(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "large-source.raw"
    source_path.write_bytes(b"123456789")
    monkeypatch.setattr(source_producer, "PIT_TAXONOMY_MAX_SOURCE_BYTES", 8)

    with pytest.raises(PITTaxonomySourceError, match="proof file custody failed"):
        source_producer._capture_configured_source(
            {
                "path": str(source_path),
                "http": _http("https://example.test/source", CAPTURE_NOW.isoformat()),
            },
            source_name="classification:test:oversize_saved",
            fetch_source=None,
            attempt_writer=object(),  # type: ignore[arg-type]
        )


def test_split_saved_active_source_rejects_linked_path_before_resolving(
    tmp_path: Path,
) -> None:
    target_path = tmp_path / "source.raw"
    target_path.write_bytes(b"small")
    linked_path = tmp_path / "linked.raw"
    try:
        linked_path.symlink_to(target_path)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"the current Windows token cannot create symlinks: {error}")

    with pytest.raises(PITTaxonomySourceError, match="capture attempt path contains a link"):
        source_producer._capture_configured_source(
            {
                "path": str(linked_path),
                "http": _http("https://example.test/source", CAPTURE_NOW.isoformat()),
            },
            source_name="classification:test:linked_saved",
            fetch_source=None,
            attempt_writer=object(),  # type: ignore[arg-type]
        )


def test_v1_saved_active_source_keeps_legacy_reader_shape(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.raw"
    source_path.write_bytes(b"legacy-source")
    metadata = _http("https://example.test/source", CAPTURE_NOW.isoformat())

    raw, observed_metadata, fetched = source_producer._capture_configured_source(
        {"path": str(source_path), "http": metadata},
        source_name="classification:test:legacy_saved",
        fetch_source=None,
    )

    assert raw == b"legacy-source"
    assert dict(observed_metadata) == metadata
    assert fetched is False


def test_inactive_termination_overlay_is_separate_from_active_isin_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Keep the Windows temp-path budget below MAX_PATH once the immutable
    # capture-attempt/component hierarchy is appended.
    repo_root = tmp_path / "r"
    module_path = repo_root / "data_module" / "pit_taxonomy_source_producer.py"
    module_path.parent.mkdir(parents=True)
    monkeypatch.setattr(source_producer, "__file__", str(module_path))
    source_url = "https://www.tpex.org.tw/storage/eb_data/11509/11500054131.html"
    raw = (
        '<!doctype html><html><head><meta http-equiv="Content-Type" '
        'content="text/html; charset=utf-8"></head><body>'
        "<div>發文日期：中華民國115年9月3日</div>"
        "<p>公告台灣精星科技股份有限公司上櫃之有價證券（股票代號：8183，"
        "以下簡稱精星公司）自115年9月23日起停止櫃檯買賣，並自115年10月1日起終止櫃檯買賣。</p>"
        "<p>精星公司每1股普通股換發精成科公司普通股。</p></body></html>"
    ).encode("utf-8")
    captured_at = "2026-09-30T21:23:55.086807+00:00"
    metadata = {
        "schema_version": "pit-8183-bounded-http-diagnostic.v1",
        "request_url": source_url,
        "method": "GET",
        "started_at": "2026-09-30T21:23:53.756235+00:00",
        "timeout_seconds": 25,
        "max_response_bytes": 8 * 1024 * 1024,
        "redirects_followed": False,
        "status_code": 200,
        "final_url": source_url,
        "content_type": "text/html",
        "charset": None,
        "content_length_header": str(len(raw)),
        "body_bytes": len(raw),
        "body_sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
        "body_complete": True,
        "body_file": "announcement.html",
        "body_kind": "official_announcement_candidate",
        "error": None,
        "completed_at": captured_at,
    }
    source_dir = repo_root / "output" / "qa" / "inactive_notice" / "attempt-1"
    source_dir.mkdir(parents=True)
    raw_path = source_dir / "announcement.html"
    metadata_path = source_dir / "metadata.json"
    raw_path.write_bytes(raw)
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    source_spec: dict[str, object] = {
        "source_version": "tpex-termination-notice-2026-09-03.v1",
        "source_url": source_url,
        "symbol": "8183",
        "issuer_name": "台灣精星科技股份有限公司",
        "market_scope": "tpex_otc",
        "published_on": "2026-09-03",
        "suspension_effective_on": "2026-09-23",
        "termination_effective_on": "2026-10-01",
        "saved_evidence": {
            "raw_path": str(raw_path),
            "metadata_path": str(metadata_path),
        },
    }
    config: dict[str, object] = {
        "classification": {},
        "security": {},
        "inactive_security": {"tpex_8183_termination": source_spec},
    }
    capture_date = date(2026, 10, 1)
    planned = source_producer._plan_configured_components(
        config, {}, capture_date
    )
    assert [item["source_name"] for item in planned] == [
        "inactive_security:tpex_8183_termination",
        "inactive_security:tpex_8183_termination:capture_metadata",
    ]
    started_at = datetime.fromisoformat("2026-10-01T05:30:00+08:00")
    custody_at = datetime.fromisoformat("2026-10-01T05:36:00+08:00")
    scope_binding: dict[str, object] = {
        "scope_binding_schema_version": source_producer.PIT_TAXONOMY_SCOPE_BINDING_SCHEMA_VERSION,
        "denominator_binding": {"symbol_count": 1, "coverage_start": capture_date.isoformat()},
        "rule_candidate_binding": {
            "universe_hash": "sha256:" + "1" * 64,
            "candidate_count": 1,
            "activation_trading_day": capture_date.isoformat(),
            "decision_at": "2026-10-01T08:30:00+08:00",
        },
        "scope_diff": source_producer._scope_diff(("8183",), ("8183",)),
        "taxonomy_coverage_complete": True,
        "rule_scope_compatible": True,
    }
    attempt = source_producer._PITTaxonomyCaptureAttempt(
        publication_root=repo_root / "p",
        capture_date=capture_date,
        attempt_id="a" * 32,
        started_at=started_at,
        scope_binding=scope_binding,
        universe_hash="sha256:" + "1" * 64,
        clock_id="clock:inactive-fixture",
        clock_manifest_hash="sha256:" + "2" * 64,
        source_config_hash="sha256:" + "3" * 64,
        planned_sources=planned,
        custody_now=lambda: custody_at,
    )
    inputs, live_fetch = source_producer._capture_configured_inactive_security_sources(
        config=config,
        capture_date=capture_date,
        request_started_at=started_at,
        fetch_source=None,
        attempt_writer=attempt,
    )
    assert live_fetch is False
    binding = attempt.seal_inputs()
    overlays = source_producer._verified_inactive_overlay_map(
        inputs,
        capture_attempt_binding=binding,
        publication_root=attempt.publication_root,
        capture_date=capture_date,
        expected_symbols=("8183",),
        market_by_symbol={"8183": "tpex_otc"},
        security_records=(),
    )
    proof = overlays["8183"]["proof"]
    assert isinstance(proof, dict)
    assert proof["state"] == "proven_inactive_common_stock"
    assert proof["eligible"] is False
    assert proof["formal_credit"] is False
    assert proof["historical_pit"] is False
    assert proof["active_security_record"] is False
    assert proof["isin_code"] is None and proof["cfi_code"] is None

    conflicting = source_producer.OfficialSecurityRecord(
        symbol="8183",
        market_scope="tpex_otc",
        section="Stocks",
        security_type="common_equity",
        cfi_code="ESVUFR",
        isin_code="TW0008183000",
        security_name="fixture active",
        market_label="TPEx",
        industry_group="fixture",
        row_hash="sha256:" + "9" * 64,
    )
    with pytest.raises(PITTaxonomySourceError, match="conflicts with active ISIN row"):
        source_producer._verified_inactive_overlay_map(
            inputs,
            capture_attempt_binding=binding,
            publication_root=attempt.publication_root,
            capture_date=capture_date,
            expected_symbols=("8183",),
            market_by_symbol={"8183": "tpex_otc"},
            security_records=(conflicting,),
        )


def test_split_capture_attempt_rejects_over_limit_source_plan_before_fetch(
    tmp_path: Path,
) -> None:
    publication_root = tmp_path / "publication"
    capture_date = DECISION_AT.date()
    bundle_root = (
        publication_root
        / "pit_taxonomy_preopen_split_v2"
        / capture_date.isoformat()
    )
    fetch_calls: list[str] = []
    config: dict[str, object] = {
        "classification": {},
        "security": {
            f"source_{index}": {"url": f"https://example.invalid/{index}"}
            for index in range(source_producer.PIT_TAXONOMY_CAPTURE_MAX_COMPONENTS + 1)
        },
    }
    scope_binding: dict[str, object] = {
        "scope_binding_schema_version": source_producer.PIT_TAXONOMY_SCOPE_BINDING_SCHEMA_VERSION,
        "denominator_binding": {},
        "rule_candidate_binding": {},
        "scope_diff": {},
        "taxonomy_coverage_complete": True,
        "rule_scope_compatible": False,
    }
    with pytest.raises(PITTaxonomySourceError, match="component-count limit") as captured:
        capture_configured_daily_pit_taxonomy_bundle(
            config=config,
            bundle_root=bundle_root,
            capture_date=capture_date,
            decision_at=DECISION_AT,
            now=datetime.fromisoformat("2026-08-25T07:55:00+08:00"),
            expected_symbols=("1101",),
            universe_hash="sha256:" + "1" * 64,
            universe_hash_symbols=("1101",),
            scores_bp=(8000,),
            rank_order=("1101",),
            clock_id="clock:fixture",
            clock_manifest_hash="sha256:" + "2" * 64,
            clock_payload={},
            universe_identity_payload={},
            company_raw_payloads={},
            company_http={},
            scope_binding=scope_binding,
            fetch_source=lambda url: fetch_calls.append(url),
            capture_attempt_id="d" * 32,
            now_provider=lambda: datetime.fromisoformat("2026-08-25T08:00:00+08:00"),
        )
    assert fetch_calls == []
    attempt_info = getattr(captured.value, "capture_attempt")
    attempt_root = Path(attempt_info["path"])
    terminal = source_producer.read_pit_taxonomy_capture_attempt(attempt_root)
    assert terminal["status"] == "failed"
    assert terminal["component_count"] == 0

def test_composite_normalization_rejects_primary_base_payload_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads = _twse_b1212_composite_fixture_payloads()
    _stub_twse_b1212_pdf_text(monkeypatch, payloads)
    definition = parse_official_twse_b1212_composite_classification_definition(
        base_raw_payload=payloads["base_definition"],
        change_raw_payload=payloads["change_notice"],
        revision_history_raw_payload=payloads["revision_history"],
        current_regulation_raw_payload=payloads["current_regulation"],
        classification_version="twse-industry-definition.v1",
        source_id="official:twse:broker-manual:O-126-A10",
        source_version="B.12.12-rederived",
        effective_from=date(2026, 5, 1),
        effective_date_basis="official_manual_implementation_record",
        effective_date_evidence=_composite_evidence(),
    )
    component_http = {
        name: _http(
            f"https://example.invalid/{name}",
            f"2026-08-25T05:0{index}:00+08:00",
            "application/pdf" if payloads[name].startswith(b"%PDF") else "text/html",
        )
        for index, name in enumerate(
            ("base_definition", "change_notice", "revision_history", "current_regulation")
        )
    }
    bad_components = {
        name: payloads[name]
        for name in (
            "base_definition",
            "change_notice",
            "revision_history",
            "current_regulation",
        )
    }
    bad_components["base_definition"] = b"%PDF-DIFFERENT-BASE"
    with pytest.raises(
        PITTaxonomySourceError,
        match="base_definition payload does not match primary",
    ):
        source_producer._normalize_definitions(
            {"twse_listed": definition},
            company_source_by_market={"twse": {"market": "twse_listed"}},
            classification_payloads={"twse_listed": payloads["base_definition"]},
            classification_http={
                "twse_listed": _http(
                    "https://example.invalid/base_definition",
                    "2026-08-25T05:00:00+08:00",
                    "application/pdf",
                )
            },
            classification_component_payloads={"twse_listed": bad_components},
            classification_component_http={"twse_listed": component_http},
            observed=datetime.fromisoformat("2026-08-25T07:55:00+08:00"),
            cutoff=datetime.fromisoformat("2026-08-25T08:30:00+08:00"),
            capture_date=date(2026, 8, 25),
        )


def test_pdf_runtime_requires_applicability_evidence_even_when_mapping_parses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_pdf_definition_parser(
        monkeypatch,
        "版本 B.12.13\nB12.13 115/05 修改 115/12 實施",
    )
    with pytest.raises(OfficialTaxonomyDefinitionError, match="effective-date evidence"):
        parse_official_classification_definition(
            b"%PDF research-only",
            market_scope="twse_listed",
            classification_version="tw-industry-explicit-map.v1",
            source_id="official:twse:broker-manual",
            source_version="B.12.13-202612",
            effective_from=date(2026, 9, 15),
        )


def test_pdf_known_future_manual_cannot_be_backdated_by_effective_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_pdf_definition_parser(
        monkeypatch,
        "版本 B.12.13\nB12.13 115/05 修改 115/12 實施",
    )
    with pytest.raises(OfficialTaxonomyDefinitionError, match="applicability is unresolved"):
        parse_official_classification_definition(
            b"%PDF research-only",
            market_scope="twse_listed",
            classification_version="tw-industry-explicit-map.v1",
            source_id="official:twse:broker-manual",
            source_version="B.12.13-202612",
            effective_from=date(2026, 9, 15),
            effective_date_basis="official_manual_implementation_record",
            effective_date_evidence=_effective_date_evidence(),
        )


def test_unknown_current_pdf_with_known_history_is_runtime_ineligible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_pdf_definition_parser(
        monkeypatch,
        "版本 B.12.14\nB12.13 115/05 修改 115/12 實施\n"
        "B12.12 115/04 修改 115/04 實施",
    )
    with pytest.raises(OfficialTaxonomyDefinitionError, match="runtime-ineligible"):
        parse_official_classification_definition(
            b"%PDF research-only",
            market_scope="twse_listed",
            classification_version="tw-industry-explicit-map.v1",
            source_id="official:twse:broker-manual",
            source_version="B.12.13-202612",
            effective_from=date(2026, 9, 15),
            effective_date_basis="official_manual_implementation_record",
            effective_date_evidence=_effective_date_evidence(),
        )


def test_pdf_research_parser_can_be_explicitly_used_before_runtime_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_pdf_definition_parser(
        monkeypatch,
        "版本 B.12.13\nB12.13 115/05 修改 115/12 實施",
    )
    definition = parse_official_classification_definition(
        b"%PDF research-only",
        market_scope="twse_listed",
        classification_version="tw-industry-explicit-map.v1",
        source_id="official:twse:broker-manual",
        source_version="B.12.13-202612",
        effective_from=date(2026, 9, 15),
        require_effective_date_evidence=False,
    )
    assert definition.mapping == {"01": "水泥工業"}
    assert definition.effective_date_basis is None


def test_tpex_current_pdf_passes_with_verified_implementation_month(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_pdf_definition_parser(
        monkeypatch,
        "版 本 V.12.18\nV12.18 115/4 修改 115/05/18 實施",
    )
    definition = parse_official_classification_definition(
        b"%PDF research-only",
        market_scope="tpex_otc",
        classification_version="tpex-industry-definition.v1",
        source_id="official:tpex:broker-manual",
        source_version="V.12.18",
        effective_from=date(2026, 9, 15),
        effective_date_basis="official_manual_implementation_record",
        effective_date_evidence=_effective_date_evidence(
            source_id="official:tpex:broker-manual",
            source_version="V.12.18",
        ),
    )
    assert definition.mapping == {"01": "水泥工業"}
    assert definition.effective_date_basis == "official_manual_implementation_record"


def test_twse_month_only_implementation_is_safe_only_after_next_month_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_pdf_definition_parser(
        monkeypatch,
        "版本 B.12.13\nB12.13 115/05 修改 115/12 實施",
    )
    with pytest.raises(OfficialTaxonomyDefinitionError, match="applicability is unresolved"):
        parse_official_classification_definition(
            b"%PDF research-only",
            market_scope="twse_listed",
            classification_version="tw-industry-explicit-map.v1",
            source_id="official:twse:broker-manual",
            source_version="B.12.13-202612",
            effective_from=date(2026, 12, 31),
            effective_date_basis="official_manual_implementation_record",
            effective_date_evidence=_effective_date_evidence(
                effective_from="2026-12-31",
            ),
        )
    definition = parse_official_classification_definition(
        b"%PDF research-only",
        market_scope="twse_listed",
        classification_version="tw-industry-explicit-map.v1",
        source_id="official:twse:broker-manual",
        source_version="B.12.13-202612",
        effective_from=date(2027, 1, 1),
        effective_date_basis="official_manual_implementation_record",
        effective_date_evidence=_effective_date_evidence(
            effective_from="2027-01-01",
        ),
    )
    assert definition.effective_from == date(2027, 1, 1)


def test_producer_reparse_does_not_accept_research_pdf_definition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_pdf_definition_parser(
        monkeypatch,
        "版本 B.12.13\nB12.13 115/05 修改 115/12 實施",
    )
    research_definition = parse_official_classification_definition(
        b"%PDF research-only",
        market_scope="twse_listed",
        classification_version="twse-industry-definition.v1",
        source_id="official:twse:broker-manual",
        source_version="B.12.13-202612",
        effective_from=date(2026, 9, 15),
        require_effective_date_evidence=False,
    )
    with pytest.raises(PITTaxonomySourceError, match="cannot be re-derived"):
        source_producer._normalize_definitions(
            {"twse_listed": research_definition},
            company_source_by_market={"twse_listed": {"market": "twse_listed"}},
            classification_payloads={"twse_listed": b"%PDF research-only"},
            classification_http={
                "twse_listed": _http(
                    "https://dsp.twse.com.tw/official-manual.pdf",
                    "2026-09-15T07:00:00+08:00",
                    "application/pdf",
                )
            },
            observed=datetime.fromisoformat("2026-09-15T07:55:00+08:00"),
            cutoff=datetime.fromisoformat("2026-09-15T08:30:00+08:00"),
            capture_date=date(2026, 9, 15),
        )


def test_security_adapter_preserves_emerging_scope_and_ignores_address_as_tdr() -> None:
    records = parse_official_isin_security_source(
        (
            '{"rows":[{"symbol":"6000","isin_code":"TW0006000001",'
            '"market":"TPEx Emerging","section":"Stocks",'
            '"security_type":"","cfi_code":"ESVUFR",'
            '"remarks":"registered address"}]}'
        ).encode("utf-8")
    )
    assert len(records) == 1
    record = records[0]
    assert record.market_scope == "tpex_emerging"
    assert record.security_type == "common_equity"
    assert record.eligible_common_equity is True


def test_security_html_requires_full_numeric_code_token() -> None:
    records = parse_official_isin_security_source(
        """
        <table>
          <tr><th>ISIN Code</th><th>Security Code</th><th>Security Name</th>
              <th>Market</th><th>Type of security</th><th>Industrial Group</th>
              <th>CFICode</th><th>Remarks</th></tr>
          <tr><td>TW0007000001</td><td>HA7000</td><td>Prefix Bond</td>
              <td>TWSE LISTED</td><td>Stocks</td><td></td><td>ESVUFR</td><td></td></tr>
          <tr><td>TW0007001009</td><td>7001B　TCCPSB</td><td>Suffix Preferred</td>
              <td>TWSE LISTED</td><td>Stocks</td><td></td><td>ESVUFR</td><td></td></tr>
          <tr><td>TW0007002007</td><td>7002　Common Name</td><td>Common Name</td>
              <td>TWSE LISTED</td><td>Stocks</td><td></td><td>ESVUFR</td><td></td></tr>
        </table>
        """.encode("utf-8")
    )
    assert [record.symbol for record in records] == ["7002"]
    assert records[0].security_name == "Common Name"


def test_security_map_allows_consistent_cross_source_duplicate_but_not_conflicts() -> None:
    def parse(rows: str) -> tuple[object, ...]:
        return parse_official_isin_security_source(
            ("{\"rows\":" + rows + "}").encode("utf-8")
        )

    duplicate_a = parse(
        '[{"symbol":"6002","isin_code":"TW0006002007",'
        '"security_name":"Alpha A","market":"TWSE LISTED",'
        '"section":"Stocks","security_type":"Stocks","cfi_code":"ESVUFR"}]'
    )
    duplicate_b = parse(
        '[{"symbol":"6002","isin_code":"TW0006002007",'
        '"security_name":"Alpha B","market":"TWSE LISTED",'
        '"section":"Stocks","security_type":"Stocks","cfi_code":"ESVUFR"}]'
    )
    types, eligibility, selected = build_security_evidence_map(
        duplicate_a + duplicate_b,
        expected_symbols=("6002",),
        market_by_symbol={"6002": "twse_listed"},
    )
    assert types == {"6002": "common_equity"}
    assert eligibility["6002"]["eligible"] is True
    assert selected["6002"].isin_code == "TW0006002007"

    unknown_competition = parse(
        '[{"symbol":"6003","isin_code":"TW0006003005",'
        '"market":"TWSE LISTED","section":"Stocks",'
        '"security_type":"Stocks","cfi_code":"ESVUFR"},'
        '{"symbol":"6003","isin_code":"TW0006003013",'
        '"market":"TWSE LISTED","section":"Stocks",'
        '"security_type":"Unclassified","cfi_code":"ABCD12"}]'
    )
    with pytest.raises(OfficialSecurityTypingError, match="conflicts"):
        build_security_evidence_map(
            unknown_competition,
            expected_symbols=("6003",),
            market_by_symbol={"6003": "twse_listed"},
        )

    same_isin_conflict = parse(
        '[{"symbol":"6004","isin_code":"TW0006004003",'
        '"market":"TWSE LISTED","section":"Stocks",'
        '"security_type":"Stocks","cfi_code":"ESVUFR"},'
        '{"symbol":"6004","isin_code":"TW0006004003",'
        '"market":"TWSE LISTED","section":"Stocks",'
        '"security_type":"Bond","cfi_code":"DNFTFR"}]'
    )
    with pytest.raises(OfficialSecurityTypingError, match="conflicts"):
        build_security_evidence_map(
            same_isin_conflict,
            expected_symbols=("6004",),
            market_by_symbol={"6004": "twse_listed"},
        )

    multiple_common = parse(
        '[{"symbol":"6005","isin_code":"TW0006005000",'
        '"market":"TWSE LISTED","section":"Stocks",'
        '"security_type":"Stocks","cfi_code":"ESVUFR"},'
        '{"symbol":"6005","isin_code":"TW0006005018",'
        '"market":"TWSE LISTED","section":"Stocks",'
        '"security_type":"Stocks","cfi_code":"ESVUFR"}]'
    )
    with pytest.raises(OfficialSecurityTypingError, match="conflicts"):
        build_security_evidence_map(
            multiple_common,
            expected_symbols=("6005",),
            market_by_symbol={"6005": "twse_listed"},
        )


def test_unaccepted_license_keeps_technical_bundle_but_blocks_industry_filter(
    tmp_path: Path,
) -> None:
    result, _ = _build_bundle(tmp_path, license_accepted=False)
    published = publish_daily_pit_taxonomy_sidecar(
        bundle_manifest_path=result.bundle_manifest_path,
        publication_root=tmp_path / "publication",
        decision_at=CAPTURE_NOW,
        now=CAPTURE_NOW,
    )
    assert published["status"] == "blocked"
    assert published["industry_filter_usable"] is False
    assert "membership_taxonomy_license_not_formally_accepted" in published["blockers"]


def test_known_tdr_is_excluded_but_foreign_common_equity_remains_eligible(
    tmp_path: Path,
) -> None:
    parent = build_pit_fixture(tmp_path / "parent", symbols=("1101", "2330"))
    parent_identity = dict(load_json(parent.universe_identity_path))
    parent_identity["universe_hash_symbols"] = ["1101", "2330"]
    definition_payload = '{"mapping":{"01":"水泥工業","24":"半導體業"}}\n'.encode(
        "utf-8"
    )
    definition = parse_official_classification_definition(
        definition_payload,
        market_scope="twse_listed",
        classification_version="tw-industry-explicit-map.v1",
        source_id="official:twse:industry-definition",
        source_version="2026-08-25",
        effective_from=DECISION_AT.date(),
    )
    result = build_daily_pit_taxonomy_bundle(
        bundle_root=tmp_path / "bundle",
        capture_date=DECISION_AT.date(),
        decision_at=DECISION_AT,
        now=datetime.fromisoformat("2026-08-25T07:55:00+08:00"),
        expected_symbols=("1101", "2330"),
        universe_hash=str(load_json(parent.universe_identity_path)["universe_hash"]),
        universe_hash_symbols=("1101", "2330"),
        scores_bp=(8000, 8001),
        rank_order=("2330", "1101"),
        clock_id=str(load_json(parent.clock_path)["clock_id"]),
        clock_manifest_hash=str(load_json(parent.clock_path)["manifest_hash"]),
        clock_payload=load_json(parent.clock_path),
        universe_identity_payload=parent_identity,
        universe_symbols_payload=load_json(parent.universe_symbols_path),
        company_raw_payloads={"twse": parent.raw_path.read_bytes()},
        company_http={
            "twse": _http(
                "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
                "2026-08-25T05:00:00+08:00",
            )
        },
        classification_payloads={"twse_listed": definition_payload},
        classification_definitions={"twse_listed": definition},
        classification_http={
            "twse_listed": _http(
                "https://dsp.twse.com.tw/static/industry-definition.pdf",
                "2026-08-25T05:05:00+08:00",
                "application/pdf",
            )
        },
        security_raw_payloads={"twse_listed": _security_html(tdr_and_foreign_common=True)},
        security_http={
            "twse_listed": _http(
                "https://isin.twse.com.tw/isin/e_single_main.jsp",
                "2026-08-25T05:10:00+08:00",
                "text/html",
            )
        },
        license_scope={
            "status": "owner_accepted_research_scope",
            "formal_acceptance_granted": True,
            "acceptance_id": "qa-taxon-tdr-foreign-20260825",
            "accepted_by": "qa-owner",
            "decision_at": DECISION_AT.isoformat(),
            "allowed_use_cases": ["formal_pit_sector_membership"],
            "redistribution_allowed": False,
        },
    )
    published = publish_daily_pit_taxonomy_sidecar(
        bundle_manifest_path=result.bundle_manifest_path,
        publication_root=tmp_path / "publication",
        decision_at=CAPTURE_NOW,
        now=CAPTURE_NOW,
    )
    assert published["status"] == "formal_source_publication"
    assert published["industry_filter_usable"] is True
    assert published["eligible_symbol_count"] == 1
    assert published["excluded_symbol_count"] == 1
    assert published["unknown_symbol_count"] == 0
    lineage = published["lineage"]
    assert isinstance(lineage, dict)
    taxonomy_identity = lineage["taxonomy_identity"]
    assert isinstance(taxonomy_identity, dict)
    assert taxonomy_identity["security_type_by_symbol"]["1101"] == "tdr"
    assert taxonomy_identity["security_type_by_symbol"]["2330"] == "common_equity"
    assert taxonomy_identity["eligible_symbols"] == ["2330"]
    assert taxonomy_identity["excluded_by_security"] == ["1101"]
