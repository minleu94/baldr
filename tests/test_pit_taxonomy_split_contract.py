from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import data_module.pit_taxonomy_source_producer as source_producer
from data_module.prospective_formal_clock import canonical_json
from tests.pit_test_support import _sha256_json


TAIPEI = ZoneInfo("Asia/Taipei")
CAPTURE_DATE = date(2026, 8, 25)
DECISION_AT = datetime(2026, 8, 25, 8, 30, tzinfo=TAIPEI)
OBSERVED_AT = datetime(2026, 8, 25, 7, 55, tzinfo=TAIPEI)
DENOMINATOR_OBSERVED_AT = datetime(2026, 8, 25, 7, 20, tzinfo=TAIPEI)
DENOMINATOR_SYMBOLS = ["1101", "2330"]
CANDIDATE_SYMBOLS = ["1101", "5371"]
HASH_SYMBOL_ORDER = ["5371", "1101"]
SCORES_BP = [9100, 8000]
DATA_AS_OF = "2026-08-24"
MAX_AVAILABLE = "2026-08-24T12:25:00+00:00"


def _write_canonical(path: Path, payload: object) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical_json(payload).encode("utf-8")
    path.write_bytes(raw)
    return raw


def _sha256_bytes(raw: bytes) -> str:
    import hashlib

    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _make_verified_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, dict[str, object], dict[str, Path]]:
    publication_root = tmp_path / "publication"
    taxonomy_bundle_root = (
        publication_root
        / "pit_taxonomy_preopen_split_v2"
        / CAPTURE_DATE.isoformat()
    )
    bundle_manifest_path = taxonomy_bundle_root / "bundle_manifest.json"
    bundle_manifest_path.parent.mkdir(parents=True)

    denominator_path = (
        publication_root
        / "pit_denominator"
        / f"{CAPTURE_DATE.isoformat()}-run-test"
        / "denominator.json"
    )
    denominator_raw = _write_canonical(
        denominator_path,
        {"fixture": "denominator raw bytes pinned by this unit test"},
    )
    denominator_payload: dict[str, object] = {
        "symbols": list(DENOMINATOR_SYMBOLS),
        "content_sha256": _sha256_json({"fixture": "denominator-content"}),
        "symbols_hash": _sha256_json(DENOMINATOR_SYMBOLS),
        "scope": "prospective_pit_sector_membership",
        "coverage_start": CAPTURE_DATE.isoformat(),
        "observed_at": DENOMINATOR_OBSERVED_AT.isoformat(),
    }
    monkeypatch.setattr(
        source_producer,
        "_precheck_denominator_child_custody",
        lambda _root, _payload: None,
    )
    monkeypatch.setattr(
        source_producer,
        "validate_prospective_pit_denominator",
        lambda _path, *, now: dict(denominator_payload),
    )

    rule_bundle_root = publication_root / "rule_source" / "fixture-rule-bundle"
    universe_hash = _sha256_json(
        {
            "schema_version": "manual-rule-only-universe.v1",
            "symbols": HASH_SYMBOL_ORDER,
            "scores_bp": SCORES_BP,
        }
    )
    source_payload = {
        "schema_version": "manual-rule-only-daily-price-window.v1",
        "source_id": "daily_prices",
        "decision_session": CAPTURE_DATE.isoformat(),
        "session_dates": [DATA_AS_OF],
        "records": [{"symbol": "1101", "date": DATA_AS_OF}],
    }
    source_window_hash = _sha256_json(source_payload)
    source_window = {
        "schema_version": "formal-rule-source-window.v1",
        "source_payload": source_payload,
        "source_window_hash": source_window_hash,
        "data_as_of_date": DATA_AS_OF,
        "max_available_timestamp": MAX_AVAILABLE,
        "capture_boundary": "daily_prices.date < decision_session",
    }
    source_window_raw = _write_canonical(
        rule_bundle_root / "source" / "daily_price_window.json",
        source_window,
    )
    symbols_raw = _write_canonical(
        rule_bundle_root / "metadata" / "universe_symbols.json",
        CANDIDATE_SYMBOLS,
    )
    clock_body: dict[str, object] = {
        "schema_version": "prospective-formal-clock.v1",
        "clock_id": "clock:prospective:20260825:split-test",
        "activation_trading_day": CAPTURE_DATE.isoformat(),
        "universe_hash": universe_hash,
    }
    clock = {
        **clock_body,
        "manifest_hash": _sha256_json(clock_body),
    }
    clock_raw = _write_canonical(
        rule_bundle_root / "clock" / "manifest.json",
        clock,
    )
    identity: dict[str, object] = {
        "schema_version": "manual-rule-only-universe.v1",
        "source_id": "daily_prices",
        "universe_hash": universe_hash,
        "symbols": CANDIDATE_SYMBOLS,
        "universe_hash_symbols": HASH_SYMBOL_ORDER,
        "scores_bp": SCORES_BP,
        "rank_order": HASH_SYMBOL_ORDER,
        "candidate_count": len(CANDIDATE_SYMBOLS),
        "data_as_of_date": DATA_AS_OF,
        "max_available_timestamp": MAX_AVAILABLE,
        "source_window_hash": source_window_hash,
        "source_window_file_hash": _sha256_bytes(source_window_raw),
        "parent_clock_manifest_file_hash": "sha256:" + "a" * 64,
    }
    identity["identity_hash"] = _sha256_json(identity)
    identity_raw = _write_canonical(
        rule_bundle_root / "metadata" / "universe_identity.json",
        identity,
    )
    raw_hashes = {
        "identity": _sha256_bytes(identity_raw),
        "symbols": _sha256_bytes(symbols_raw),
        "clock": _sha256_bytes(clock_raw),
        "source_window": _sha256_bytes(source_window_raw),
    }
    denominator_relative = denominator_path.relative_to(publication_root).as_posix()
    rule_relative = rule_bundle_root.relative_to(publication_root).as_posix()
    candidate_binding: dict[str, object] = {
        "schema_version": "pit-rule-candidate-binding.v1",
        "bundle_path": rule_relative,
        "file_hashes": raw_hashes,
        "identity_hash": identity["identity_hash"],
        "clock_id": clock["clock_id"],
        "clock_manifest_hash": clock["manifest_hash"],
        "universe_hash": universe_hash,
        "candidate_count": len(CANDIDATE_SYMBOLS),
        "candidate_symbols_hash": _sha256_json(CANDIDATE_SYMBOLS),
        "activation_trading_day": CAPTURE_DATE.isoformat(),
        "decision_at": DECISION_AT.isoformat(),
        "data_as_of_date": DATA_AS_OF,
        "max_available_timestamp": MAX_AVAILABLE,
        "source_window_hash": source_window_hash,
    }
    diff = source_producer._scope_diff(
        DENOMINATOR_SYMBOLS,
        CANDIDATE_SYMBOLS,
    )
    scope_binding: dict[str, object] = {
        "scope_binding_schema_version": (
            source_producer.PIT_TAXONOMY_SCOPE_BINDING_SCHEMA_VERSION
        ),
        "denominator_binding": {
            "schema_version": "pit-prospective-pit-denominator-binding.v1",
            "path": denominator_relative,
            "file_sha256": _sha256_bytes(denominator_raw),
            "content_sha256": denominator_payload["content_sha256"],
            "symbols_hash": denominator_payload["symbols_hash"],
            "symbol_count": len(DENOMINATOR_SYMBOLS),
            "scope": denominator_payload["scope"],
            "coverage_start": denominator_payload["coverage_start"],
            "observed_at": denominator_payload["observed_at"],
        },
        "rule_candidate_binding": candidate_binding,
        "scope_diff": diff,
        "taxonomy_coverage_complete": True,
        "rule_scope_compatible": False,
    }
    bundle: dict[str, object] = {
        **scope_binding,
        "symbols": list(DENOMINATOR_SYMBOLS),
        "universe_hash_symbols": list(HASH_SYMBOL_ORDER),
        "scores_bp": list(SCORES_BP),
        "rank_order": list(HASH_SYMBOL_ORDER),
        "universe_hash": universe_hash,
        "clock_id": clock["clock_id"],
        "clock_manifest_hash": clock["manifest_hash"],
        "capture_started_at": OBSERVED_AT.isoformat(),
    }
    paths = {
        "denominator": denominator_path,
        "identity": rule_bundle_root / "metadata" / "universe_identity.json",
        "symbols": rule_bundle_root / "metadata" / "universe_symbols.json",
        "clock": rule_bundle_root / "clock" / "manifest.json",
        "source_window": rule_bundle_root / "source" / "daily_price_window.json",
    }
    return bundle_manifest_path, bundle, paths


def _verify(
    bundle_manifest_path: Path,
    bundle: dict[str, object],
) -> dict[str, object]:
    return source_producer._verify_split_scope_binding(
        bundle,
        bundle_manifest_path=bundle_manifest_path,
        capture_date=CAPTURE_DATE,
        decision_at=DECISION_AT,
        observed_at=OBSERVED_AT,
    )


def test_split_contract_revalidates_sources_and_preserves_rule_only_diff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle_path, bundle, _paths = _make_verified_fixture(tmp_path, monkeypatch)

    proof = _verify(bundle_path, bundle)

    assert proof["taxonomy_coverage_complete"] is True
    assert proof["rule_scope_compatible"] is False
    diff = proof["scope_diff"]
    assert isinstance(diff, dict)
    assert diff["intersection_symbols"] == ["1101"]
    assert diff["denominator_only_symbols"] == ["2330"]
    assert diff["rule_only_symbols"] == ["5371"]


def test_split_contract_fails_closed_for_missing_denominator_or_rule_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle_path, bundle, paths = _make_verified_fixture(
        tmp_path / "denominator", monkeypatch
    )
    paths["denominator"].unlink()
    with pytest.raises(source_producer.PITTaxonomySourceError, match="escapes or is missing"):
        _verify(bundle_path, bundle)

    hash_path, hash_bundle, _ = _make_verified_fixture(
        tmp_path / "rule-hash", monkeypatch
    )
    candidate_binding = hash_bundle["rule_candidate_binding"]
    assert isinstance(candidate_binding, dict)
    file_hashes = dict(candidate_binding["file_hashes"])
    file_hashes.pop("identity")
    candidate_binding["file_hashes"] = file_hashes
    with pytest.raises(source_producer.PITTaxonomySourceError, match="raw file hash set is incomplete"):
        _verify(hash_path, hash_bundle)


def test_split_contract_rejects_missing_rule_timestamp_and_wrong_clock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_path, missing_bundle, paths = _make_verified_fixture(
        tmp_path / "timestamp", monkeypatch
    )
    identity = json.loads(paths["identity"].read_text(encoding="utf-8"))
    identity.pop("max_available_timestamp")
    identity.pop("identity_hash")
    identity["identity_hash"] = _sha256_json(identity)
    identity_raw = _write_canonical(paths["identity"], identity)
    candidate_binding = missing_bundle["rule_candidate_binding"]
    assert isinstance(candidate_binding, dict)
    file_hashes = dict(candidate_binding["file_hashes"])
    file_hashes["identity"] = _sha256_bytes(identity_raw)
    candidate_binding["file_hashes"] = file_hashes
    candidate_binding["identity_hash"] = identity["identity_hash"]
    with pytest.raises(source_producer.PITTaxonomySourceError, match="max_available_timestamp"):
        _verify(missing_path, missing_bundle)

    wrong_clock_path, wrong_clock_bundle, _ = _make_verified_fixture(
        tmp_path / "wrong-clock", monkeypatch
    )
    wrong_clock_bundle["clock_id"] = "clock:prospective:wrong"
    with pytest.raises(source_producer.PITTaxonomySourceError, match="clock binding differs"):
        _verify(wrong_clock_path, wrong_clock_bundle)


def test_split_contract_detects_rule_raw_mutation_and_rejects_path_traversal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle_path, bundle, paths = _make_verified_fixture(tmp_path, monkeypatch)
    paths["source_window"].write_bytes(paths["source_window"].read_bytes() + b" ")
    with pytest.raises(source_producer.PITTaxonomySourceError, match="raw bytes changed"):
        _verify(bundle_path, bundle)

    bad_path_bundle = dict(bundle)
    denominator_binding = dict(bundle["denominator_binding"])
    denominator_binding["path"] = "pit_denominator/../outside.json"
    bad_path_bundle["denominator_binding"] = denominator_binding
    with pytest.raises(source_producer.PITTaxonomySourceError, match="normalized and relative"):
        _verify(bundle_path, bad_path_bundle)
