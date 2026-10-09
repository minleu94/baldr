from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

import data_module.pit_taxonomy_source_producer as producer
from data_module.prospective_formal_clock import canonical_json


TAIPEI = producer.TAIPEI
CAPTURE_DATE = date(2026, 10, 1)
STARTED_AT = datetime(2026, 10, 1, 7, 50, tzinfo=TAIPEI)


@pytest.mark.parametrize("reason,live,allowed", [
    ("late source config proof is missing", True, True),
    ("late source config proof is missing", False, False),
    ("source config proof cache is partial or has unexpected files", True, False),
    ("source config proof metadata hash mismatch", True, False),
])
def test_wrapper_only_materializes_missing_live_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    reason: str, live: bool, allowed: bool,
) -> None:
    from scripts.scheduled import run_pit_sector_membership_preopen_capture as scheduled
    monkeypatch.setattr(scheduled, "ROOT", tmp_path)
    reads = []
    writes = []
    def read(**kwargs: object) -> dict[str, object]:
        reads.append(kwargs)
        if len(reads) == 1:
            raise producer.PITTaxonomySourceError(reason)
        return {"status": "hash_addressed_source_config_proof_verified"}
    monkeypatch.setattr(scheduled, "read_existing_split_source_config_proof", read)
    monkeypatch.setattr(scheduled, "materialize_existing_split_source_config_proof", lambda **kwargs: writes.append(kwargs))
    path = tmp_path / (producer.PIT_TAXONOMY_LIVE_CONFIG_SOURCE_RELATIVE_PATH if live else "custom.json")
    def invoke() -> dict[str, object]:
        return scheduled._ensure_live_split_source_config_proof(
            publication_root=tmp_path / "output", bundle_path=tmp_path / "bundle.json",
            config={}, config_path=path, observed=STARTED_AT,
            now_provider=lambda: STARTED_AT + timedelta(minutes=1),
        )
    if allowed:
        assert invoke()["status"] == "hash_addressed_source_config_proof_verified"
        assert len(writes) == 1 and len(reads) == 2
    else:
        with pytest.raises(producer.PITTaxonomySourceError):
            invoke()
        assert writes == []


def _bytes_hash(raw: bytes) -> str:
    import hashlib

    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _config() -> dict[str, object]:
    return {
        "schema_version": producer.PIT_TAXONOMY_SOURCE_CONFIG_SCHEMA_VERSION,
        "classification": {
            "tpex_otc": {
                "url": "https://www.tpex.org.tw/official-classification"
            }
        },
        "security": {
            "all": {"url": "https://isin.twse.com.tw/isin/e_single_main.jsp"}
        },
        "inactive_security": {
            "tpex_8183_termination": {
                "source_url": "https://www.tpex.org.tw/storage/eb_data/11509/11500054131.html",
                "issuer_name": "台灣精星科技股份有限公司",
                "symbol": "8183",
                "market_scope": "tpex_otc",
                "published_on": "2026-09-03",
                "suspension_effective_on": "2026-09-23",
                "termination_effective_on": "2026-10-01",
                "source_version": "tpex-termination-notice-2026-09-03.v1",
                "saved_evidence": {
                    "raw_path": "diagnostic/announcement.html",
                    "metadata_path": "diagnostic/metadata.json",
                },
            }
        },
        "license_scope": {
            "formal_acceptance_granted": False,
            "redistribution_allowed": False,
            "allowed_use_cases": ["research_shadow", "diagnostics", "parser_readback"],
        },
    }


def _synthetic_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Path, dict[str, object], dict[str, object]]:
    repo = tmp_path
    publication_root = repo / "output" / "formal_daily_publications"
    bundle_root = (
        publication_root / "pit_taxonomy_preopen_split_v2" / CAPTURE_DATE.isoformat()
    )
    bundle_root.mkdir(parents=True)
    bundle_path = bundle_root / "bundle_manifest.json"
    attempt_id = "0123456789abcdef0123456789abcdef"
    attempt_relative = (
        f"pit_taxonomy_capture_attempts/{CAPTURE_DATE.isoformat()}/{attempt_id}"
    )
    attempt_root = publication_root / Path(attempt_relative)
    attempt_root.mkdir(parents=True)
    config_path = (
        repo
        / producer.PIT_TAXONOMY_LATE_CONFIG_SOURCE_RELATIVE_PATH
    )
    config_path.parent.mkdir(parents=True)
    config = _config()
    config_raw = json.dumps(
        config,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    config_path.write_bytes(config_raw)
    canonical_hash = _bytes_hash(canonical_json(config).encode("utf-8"))
    descriptor = {
        "schema_version": producer.PIT_TAXONOMY_CAPTURE_ATTEMPT_SCHEMA_VERSION,
        "attempt_id": attempt_id,
        "capture_date": CAPTURE_DATE.isoformat(),
        "source_config_sha256": canonical_hash,
        "candidate_only": True,
        "research_only": True,
        "formal_consumer_compatible": False,
        "formal_credit": False,
    }
    descriptor_raw = canonical_json(descriptor).encode("utf-8")
    descriptor_sha = _bytes_hash(descriptor_raw)
    descriptor_path = attempt_root / "attempt_descriptor.json"
    descriptor_path.write_bytes(descriptor_raw)
    receipt_raw = b"fixture receipt bytes"
    (attempt_root / "capture_receipt.json").write_bytes(receipt_raw)
    receipt_sha = _bytes_hash(receipt_raw)
    binding = {
        "schema_version": producer.PIT_TAXONOMY_CAPTURE_ATTEMPT_BINDING_SCHEMA_VERSION,
        "attempt_id": attempt_id,
        "path": attempt_relative,
        "descriptor_sha256": descriptor_sha,
        "receipt_path": f"{attempt_relative}/capture_receipt.json",
        "receipt_sha256": receipt_sha,
        "component_count": 2,
        "aggregate_raw_bytes": 100,
    }
    bundle: dict[str, object] = {
        "schema_version": producer.PIT_TAXONOMY_SPLIT_BUNDLE_SCHEMA_VERSION,
        "capture_date": CAPTURE_DATE.isoformat(),
        "captured_at": datetime(2026, 10, 1, 6, 11, tzinfo=TAIPEI).isoformat(),
        "status": "preopen_captured",
        "taxonomy_coverage_complete": True,
        "rule_scope_compatible": False,
        "formal_oos_allowed": False,
        "production_action_allowed": False,
        "promotion_eligible": False,
        "capture_attempt_binding": binding,
    }
    bundle["bundle_hash"] = producer._sha256_json(bundle)
    bundle_raw = canonical_json(bundle).encode("utf-8")
    bundle_path.write_bytes(bundle_raw)
    attempt = {
        "status": "success",
        "attempt_id": attempt_id,
        "descriptor_sha256": descriptor_sha,
        "receipt_sha256": receipt_sha,
        "terminal_result": {
            "status": "success",
            "attempt_id": attempt_id,
            "bundle_hash": bundle["bundle_hash"],
        },
    }
    monkeypatch.setattr(
        producer,
        "validate_daily_pit_taxonomy_bundle",
        lambda *_args, **_kwargs: {
            "schema_version": producer.PIT_TAXONOMY_SPLIT_BUNDLE_SCHEMA_VERSION
        },
    )
    monkeypatch.setattr(
        producer,
        "read_pit_taxonomy_capture_attempt",
        lambda *_args, **_kwargs: attempt,
    )
    return repo, publication_root, bundle_path, config, {
        "attempt": attempt,
        "attempt_root": attempt_root,
        "bundle_raw": bundle_raw,
        "config_path": config_path,
        "config_raw": config_raw,
        "canonical_hash": canonical_hash,
        "capture_date": CAPTURE_DATE,
    }


@pytest.mark.parametrize("live_config", [False, True])
def test_late_source_config_proof_materializes_readbacks_and_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    live_config: bool,
) -> None:
    repo, publication_root, bundle_path, config, fixture = _synthetic_candidate(
        tmp_path, monkeypatch
    )
    if live_config:
        config_path = repo / producer.PIT_TAXONOMY_LIVE_CONFIG_SOURCE_RELATIVE_PATH
        config_path.parent.mkdir(parents=True)
        config_path.write_bytes(fixture["config_raw"])
        fixture["config_path"] = config_path
    timestamps = iter(
        (
            datetime(2026, 10, 1, 8, 10, tzinfo=TAIPEI),
            datetime(2026, 10, 1, 8, 11, tzinfo=TAIPEI),
        )
    )
    result = producer.materialize_existing_split_source_config_proof(
        publication_root=publication_root,
        bundle_manifest_path=bundle_path,
        source_config_path=fixture["config_path"],
        repository_root=repo,
        materialized_at=STARTED_AT,
        now_provider=lambda: next(timestamps),
    )

    assert result["status"] == "late_source_config_proof_materialized"
    assert result["historical_availability_proven"] is False
    assert result["historical_pit_eligible"] is False
    assert result["formal_credit"] is False
    proof_root = Path(str(result["source_config_proof_root"]))
    assert {item.name for item in proof_root.iterdir()} == {
        "source_config.json",
        "config_proof.json",
        "completion_receipt.json",
    }
    assert (proof_root / "source_config.json").read_bytes() == fixture["config_raw"]
    assert (bundle_path).read_bytes() == fixture["bundle_raw"]
    assert (
        Path(fixture["attempt_root"]) / "attempt_descriptor.json"
    ).read_bytes() == canonical_json(
        json.loads(
            (Path(fixture["attempt_root"]) / "attempt_descriptor.json").read_text(
                encoding="utf-8"
            )
        )
    ).encode("utf-8")

    current_config = json.loads(json.dumps(config))
    current_config["inactive_security"]["tpex_8183_termination"]["saved_evidence"] = {
        "raw_path": "new/transport/path.html",
        "metadata_path": "new/transport/metadata.json",
    }
    proof = producer.read_existing_split_source_config_proof(
        publication_root=publication_root,
        bundle_manifest_path=bundle_path,
        repository_root=repo,
        current_config=current_config,
        now=datetime(2026, 10, 1, 8, 20, tzinfo=TAIPEI),
    )
    assert proof["status"] == "hash_addressed_source_config_proof_verified"
    assert proof["proof_sha256"] == result["proof_sha256"]
    assert proof["formal_credit"] is False
    with pytest.raises(
        producer.PITTaxonomySourceError,
        match="split config proof must be materialized on the candidate date",
    ):
        producer.read_existing_split_source_config_proof(
            publication_root=publication_root,
            bundle_manifest_path=bundle_path,
            repository_root=repo,
            current_config=current_config,
            now=datetime(2026, 10, 2, 7, 0, tzinfo=TAIPEI),
        )

    before = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in proof_root.iterdir()
    }
    retry = producer.materialize_existing_split_source_config_proof(
        publication_root=publication_root,
        bundle_manifest_path=bundle_path,
        source_config_path=fixture["config_path"],
        repository_root=repo,
        materialized_at=datetime(2026, 10, 1, 8, 21, tzinfo=TAIPEI),
    )
    after = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in proof_root.iterdir()
    }
    assert retry["status"] == "late_source_config_proof_already_verified"
    assert after == before


def test_late_source_config_proof_rejects_semantic_change_and_wrong_raw_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, publication_root, bundle_path, _config_value, fixture = _synthetic_candidate(
        tmp_path, monkeypatch
    )
    config = json.loads(Path(fixture["config_path"]).read_text(encoding="utf-8"))
    config["security"]["all"]["url"] = "https://isin.example.invalid/"
    Path(fixture["config_path"]).write_text(
        json.dumps(config, ensure_ascii=False), encoding="utf-8"
    )
    with pytest.raises(producer.PITTaxonomySourceError, match="canonical hash differs"):
        producer.materialize_existing_split_source_config_proof(
            publication_root=publication_root,
            bundle_manifest_path=bundle_path,
            source_config_path=fixture["config_path"],
            repository_root=repo,
            materialized_at=STARTED_AT,
        )
    cache_root = producer._source_config_proof_cache_path(
        repo,
        capture_date=CAPTURE_DATE,
        attempt_id="0123456789abcdef0123456789abcdef",
        source_config_sha256=fixture["canonical_hash"],
    )
    assert not cache_root.exists()


def test_late_source_config_proof_missing_has_precise_reuse_blocker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, publication_root, bundle_path, config, fixture = _synthetic_candidate(
        tmp_path, monkeypatch
    )
    with pytest.raises(producer.PITTaxonomySourceError, match="late source config proof is missing"):
        producer.read_existing_split_source_config_proof(
            publication_root=publication_root,
            bundle_manifest_path=bundle_path,
            repository_root=repo,
            current_config=config,
            now=datetime(2026, 10, 1, 8, 20, tzinfo=TAIPEI),
        )


def test_late_source_config_proof_refuses_to_repair_partial_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, publication_root, bundle_path, _config, fixture = _synthetic_candidate(
        tmp_path, monkeypatch
    )
    partial_root = producer._source_config_proof_cache_path(
        repo,
        capture_date=CAPTURE_DATE,
        attempt_id="0123456789abcdef0123456789abcdef",
        source_config_sha256=fixture["canonical_hash"],
    )
    partial_root.mkdir(parents=True)
    partial_raw = partial_root / "source_config.json"
    partial_raw.write_bytes(fixture["config_raw"])

    with pytest.raises(
        producer.PITTaxonomySourceError,
        match="source config proof cache is partial or has unexpected files",
    ):
        producer.materialize_existing_split_source_config_proof(
            publication_root=publication_root,
            bundle_manifest_path=bundle_path,
            source_config_path=fixture["config_path"],
            repository_root=repo,
            materialized_at=STARTED_AT,
        )
    assert partial_raw.read_bytes() == fixture["config_raw"]
    assert {item.name for item in partial_root.iterdir()} == {"source_config.json"}


def test_late_source_config_proof_rejects_mutated_raw_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, publication_root, bundle_path, config, fixture = _synthetic_candidate(
        tmp_path, monkeypatch
    )
    timestamps = iter(
        (
            datetime(2026, 10, 1, 8, 10, tzinfo=TAIPEI),
            datetime(2026, 10, 1, 8, 11, tzinfo=TAIPEI),
        )
    )
    result = producer.materialize_existing_split_source_config_proof(
        publication_root=publication_root,
        bundle_manifest_path=bundle_path,
        source_config_path=fixture["config_path"],
        repository_root=repo,
        materialized_at=STARTED_AT,
        now_provider=lambda: next(timestamps),
    )
    proof_raw = Path(str(result["source_config_raw_path"]))
    proof_raw.write_bytes(fixture["config_raw"] + b" ")

    with pytest.raises(
        producer.PITTaxonomySourceError,
        match="source config proof linkage differs from validated bundle/attempt",
    ):
        producer.read_existing_split_source_config_proof(
            publication_root=publication_root,
            bundle_manifest_path=bundle_path,
            repository_root=repo,
            current_config=config,
            now=datetime(2026, 10, 1, 8, 20, tzinfo=TAIPEI),
        )


def test_late_source_config_proof_rejects_readback_completed_after_cutoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, publication_root, bundle_path, _config_value, fixture = _synthetic_candidate(
        tmp_path, monkeypatch
    )
    timestamps = iter(
        (
            datetime(2026, 10, 1, 8, 29, 59, tzinfo=TAIPEI),
            datetime(2026, 10, 1, 8, 30, tzinfo=TAIPEI),
        )
    )
    with pytest.raises(producer.PITTaxonomySourceError, match="readback completed outside"):
        producer.materialize_existing_split_source_config_proof(
            publication_root=publication_root,
            bundle_manifest_path=bundle_path,
            source_config_path=fixture["config_path"],
            repository_root=repo,
            materialized_at=datetime(2026, 10, 1, 8, 29, 58, tzinfo=TAIPEI),
            now_provider=lambda: next(timestamps),
        )
