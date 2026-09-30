from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from scripts.scheduled import run_pit_sector_membership_preopen_capture as runner


TAIPEI = ZoneInfo("Asia/Taipei")
CAPTURE_DATE = date(2026, 10, 1)
OBSERVED = datetime(2026, 10, 1, 7, 10, tzinfo=TAIPEI)
RULE_SYMBOLS = ("1101", "5371")
DENOMINATOR_SYMBOLS = ("1101",)


def _scope_binding(
    symbols: tuple[str, ...],
    parent: dict[str, object],
) -> dict[str, object]:
    candidate_symbols = tuple(parent["expected_symbols"])
    denominator = set(symbols)
    candidates = set(candidate_symbols)
    intersection = sorted(denominator & candidates)
    denominator_only = sorted(denominator - candidates)
    rule_only = sorted(candidates - denominator)
    return {
        "scope_binding_schema_version": "pit-industry-taxonomy-scope-binding.v1",
        "denominator_binding": {
            "schema_version": "pit-prospective-pit-denominator-binding.v1",
            "path": "pit_denominator/2026-10-01-fixture/denominator.json",
            "file_sha256": "sha256:fixture-denominator-file",
            "content_sha256": "sha256:fixture-denominator-content",
            "symbols_hash": runner._sha256_json(list(symbols)),
            "symbol_count": len(symbols),
            "scope": "prospective_pit_sector_membership",
            "coverage_start": CAPTURE_DATE.isoformat(),
            "observed_at": "2026-10-01T06:00:00+08:00",
        },
        "rule_candidate_binding": {
            "schema_version": "pit-rule-candidate-binding.v1",
            "bundle_path": "rule_source/clock-fixture",
            "file_hashes": {
                "identity": "sha256:fixture-identity",
                "symbols": "sha256:fixture-symbols",
                "clock": "sha256:fixture-clock",
                "source_window": "sha256:fixture-window",
            },
            "identity_hash": "sha256:fixture-identity-content",
            "clock_id": parent["clock_id"],
            "clock_manifest_hash": parent["clock_manifest_hash"],
            "universe_hash": parent["universe_hash"],
            "candidate_count": len(candidate_symbols),
            "candidate_symbols_hash": runner._sha256_json(list(candidate_symbols)),
            "activation_trading_day": CAPTURE_DATE.isoformat(),
            "decision_at": "2026-10-01T08:30:00+08:00",
            "data_as_of_date": "2026-09-30",
            "max_available_timestamp": "2026-09-30T13:30:00+08:00",
            "source_window_hash": "sha256:fixture-window-content",
        },
        "scope_diff": {
            "denominator_count": len(denominator),
            "candidate_count": len(candidates),
            "intersection_count": len(intersection),
            "denominator_only_count": len(denominator_only),
            "rule_only_count": len(rule_only),
            "intersection_symbols": intersection,
            "intersection_symbols_hash": runner._sha256_json(intersection),
            "denominator_only_symbols": denominator_only,
            "denominator_only_symbols_hash": runner._sha256_json(denominator_only),
            "rule_only_symbols": rule_only,
            "rule_only_symbols_hash": runner._sha256_json(rule_only),
        },
        "taxonomy_coverage_complete": True,
        "rule_scope_compatible": not rule_only,
    }


def _patch_reuse_candidate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    observed: datetime = OBSERVED,
    validation_completed_at: datetime | None = None,
) -> dict[str, object]:
    publication_root = tmp_path / "publication"
    publication_root.mkdir()
    bundle_root = (
        publication_root
        / "pit_taxonomy_preopen_split_v2"
        / observed.astimezone(TAIPEI).date().isoformat()
    )
    bundle_root.mkdir(parents=True)
    bundle_path = bundle_root / "bundle_manifest.json"
    attempt_root = (
        publication_root
        / "pit_taxonomy_capture_attempts"
        / observed.astimezone(TAIPEI).date().isoformat()
        / "0123456789abcdef0123456789abcdef"
    )
    attempt_root.mkdir(parents=True)
    denominator_path = (
        publication_root
        / "pit_denominator"
        / "2026-10-01-fixture"
        / "denominator.json"
    )
    denominator_path.parent.mkdir(parents=True)
    rule_root = publication_root / "rule_source" / "clock-fixture"
    rule_root.mkdir(parents=True)

    parent: dict[str, object] = {
        "bundle_root": str(rule_root),
        "identity": {},
        "symbols_payload": list(RULE_SYMBOLS),
        "clock": {},
        "expected_symbols": RULE_SYMBOLS,
        "universe_hash_symbols": RULE_SYMBOLS,
        "scores_bp": (9000, 8000),
        "rank_order": RULE_SYMBOLS,
        "rank_order_source": "parent.universe_hash_symbols",
        "universe_hash": "sha256:fixture-universe",
        "clock_id": "clock:fixture",
        "clock_manifest_hash": "sha256:fixture-clock-manifest",
    }
    binding = _scope_binding(DENOMINATOR_SYMBOLS, parent)
    capture_attempt_binding = {
        "path": f"pit_taxonomy_capture_attempts/{observed.date().isoformat()}/0123456789abcdef0123456789abcdef",
        "attempt_id": "0123456789abcdef0123456789abcdef",
    }
    bundle: dict[str, object] = {
        **binding,
        "capture_date": observed.astimezone(TAIPEI).date().isoformat(),
        "symbols": list(DENOMINATOR_SYMBOLS),
        "universe_hash": parent["universe_hash"],
        "universe_hash_symbols": list(parent["universe_hash_symbols"]),
        "scores_bp": list(parent["scores_bp"]),
        "rank_order": list(parent["rank_order"]),
        "clock_id": parent["clock_id"],
        "clock_manifest_hash": parent["clock_manifest_hash"],
        "capture_attempt_binding": capture_attempt_binding,
        "bundle_hash": "sha256:fixture-bundle",
    }
    config: dict[str, object] = {"classification": {}, "security": {}}
    attempt: dict[str, object] = {
        "status": "success",
        "attempt_id": capture_attempt_binding["attempt_id"],
        "components": [],
    }
    descriptor = {"planned_sources": []}
    archive_raw = {"twse": b"twse-raw", "tpex": b"tpex-raw"}
    archive_http = {
        "twse": {"requested_url": "https://twse.example.invalid"},
        "tpex": {"requested_url": "https://tpex.example.invalid"},
    }
    denominator = {"symbols": list(DENOMINATOR_SYMBOLS)}
    checked: list[str] = []

    monkeypatch.setattr(runner, "_split_taxonomy_bundle_root", lambda *_args: bundle_root)
    monkeypatch.setattr(runner, "_assert_no_link_path", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        runner,
        "load_pit_taxonomy_source_config",
        lambda *_args, **_kwargs: config,
    )
    monkeypatch.setattr(
        runner,
        "read_existing_split_source_config_proof",
        lambda **_kwargs: {"config": config, "proof_sha256": "sha256:fixture-proof"},
    )
    monkeypatch.setattr(
        runner,
        "reuse_pit_candidate_archive_before_cutoff",
        lambda **_kwargs: checked.append("archive_readback")
        or {
            "durable_archive": {"archive_manifest_path": "archive_manifest.json"},
            "durable_archive_verified": True,
        },
    )
    monkeypatch.setattr(
        runner,
        "_load_archived_company_sources",
        lambda *_args, **_kwargs: (archive_raw, archive_http, {"manifest_path": "archive_manifest.json"}),
    )
    monkeypatch.setattr(
        runner,
        "_verify_split_candidate_company_archive",
        lambda **_kwargs: {"status": "verified"},
    )
    monkeypatch.setattr(
        runner,
        "_find_verified_denominator",
        lambda *_args, **_kwargs: (denominator_path, "existing_verified"),
    )
    monkeypatch.setattr(
        runner,
        "validate_prospective_pit_denominator",
        lambda *_args, **_kwargs: denominator,
    )
    monkeypatch.setattr(runner, "_find_rule_source_parent", lambda *_args, **_kwargs: parent)
    monkeypatch.setattr(
        runner,
        "_build_split_scope_binding",
        lambda **kwargs: _scope_binding(tuple(kwargs["denominator_symbols"]), kwargs["parent"]),
    )
    monkeypatch.setattr(
        runner,
        "validate_daily_pit_taxonomy_bundle",
        lambda *_args, **_kwargs: {
            "taxonomy_coverage_complete": True,
            "rule_scope_compatible": False,
        },
    )
    monkeypatch.setattr(
        runner,
        "_read_split_candidate_json",
        lambda *_args, **_kwargs: (bundle, b"bundle-bytes"),
    )
    monkeypatch.setattr(runner, "_proof_child", lambda *_args, **_kwargs: attempt_root)
    monkeypatch.setattr(runner, "read_pit_taxonomy_capture_attempt", lambda *_args, **_kwargs: attempt)
    monkeypatch.setattr(runner, "_proof_file_bytes", lambda *_args, **_kwargs: b"descriptor")
    monkeypatch.setattr(runner, "_decode_json_object_no_duplicates", lambda *_args, **_kwargs: descriptor)
    monkeypatch.setattr(
        runner,
        "_verify_reused_attempt_source_config",
        lambda **_kwargs: checked.append("attempt_config_binding"),
    )
    return {
        "publication_root": publication_root,
        "bundle_root": bundle_root,
        "bundle": bundle,
        "parent": parent,
        "denominator": denominator,
        "checked": checked,
        "archive_path": "archive_manifest.json",
        "attempt_root": attempt_root,
        "validation_completed_at": validation_completed_at or observed + timedelta(minutes=1),
    }


def test_same_day_reuse_success_stays_read_only_and_formal_false(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _patch_reuse_candidate(monkeypatch, tmp_path)
    result = runner._reuse_existing_split_taxonomy_candidate(
        publication_root=fixture["publication_root"],  # type: ignore[arg-type]
        observed=OBSERVED,
        config_path=None,
        now_provider=lambda: fixture["validation_completed_at"],  # type: ignore[return-value]
    )
    assert result["status"] == "verified_reused_existing_split_candidate"
    assert result["network_attempted"] is False
    assert result["new_attempt_created"] is False
    assert result["formal_consumer_compatible"] is False
    assert result["formal_credit"] is False
    assert result["taxonomy_coverage_complete"] is True
    assert result["rule_scope_compatible"] is False
    assert fixture["checked"] == ["archive_readback", "attempt_config_binding"]


def test_scheduled_reuse_success_writes_only_isolated_research_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publication_root = tmp_path / "publication"
    (publication_root / "pit_taxonomy_preopen_split_v2" / CAPTURE_DATE.isoformat()).mkdir(
        parents=True
    )
    status_root = publication_root / "scheduler" / "reuse-validation" / "unique-run"

    class ActualClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return OBSERVED.astimezone(tz) if tz is not None else OBSERVED

    monkeypatch.setattr(runner, "datetime", ActualClock)
    monkeypatch.setattr(runner, "formal_schedule_day_state", lambda **_kwargs: (True, "official_open"))
    monkeypatch.setattr(runner, "load_optional_formal_runtime_config", lambda **_kwargs: None)
    reuse_calls: list[str] = []

    def reusable_candidate(**kwargs):
        assert kwargs["observed"].astimezone(TAIPEI) == OBSERVED
        assert kwargs["now_provider"]().astimezone(TAIPEI) == OBSERVED
        reuse_calls.append("reuse")
        return {
            "status": "verified_reused_existing_split_candidate",
            "taxonomy_bundle_path": "split-bundle.json",
            "validation_completed_at": OBSERVED.isoformat(),
            "bundle_hash": "sha256:fixture-bundle",
            "capture_date": CAPTURE_DATE.isoformat(),
            "archive": {"manifest_path": "archive_manifest.json"},
            "denominator_path": "denominator.json",
            "rule_parent_root": "rule-source",
            "rule_universe_hash": "sha256:rule-universe",
            "capture_attempt_id": "0123456789abcdef0123456789abcdef",
            "capture_attempt_status": "success",
            "source_config_proof_sha256": "sha256:config-proof",
            "source_config_proof_materialized_at": OBSERVED.isoformat(),
            "taxonomy_coverage_complete": True,
            "rule_scope_compatible": False,
            "formal_consumer_compatible": False,
            "formal_credit": False,
            "research_only": True,
            "candidate_only": True,
            "network_attempted": False,
            "new_attempt_created": False,
        }

    monkeypatch.setattr(runner, "_reuse_existing_split_taxonomy_candidate", reusable_candidate)
    monkeypatch.setattr(
        runner,
        "reuse_pit_candidate_archive_before_cutoff",
        lambda **_kwargs: pytest.fail("reuse branch must not reacquire the archive"),
    )
    monkeypatch.setattr(
        runner,
        "_refresh_pit_denominator",
        lambda **_kwargs: pytest.fail("reuse branch must not refresh the denominator"),
    )
    monkeypatch.setattr(
        runner,
        "_capture_taxonomy_for_run",
        lambda **_kwargs: pytest.fail("reuse branch must not run taxonomy acquisition"),
    )

    payload, exit_code = runner.run_capture(
        publication_root=publication_root,
        status_root=status_root,
        split_denominator_contract=True,
    )

    assert exit_code == 0
    assert payload["status"] == "machine_verified_candidate"
    assert payload["capture_mode"] == "reused_existing_split_candidate"
    assert payload["formal_ready"] is False
    assert payload["formal_consumer_compatible"] is False
    assert payload["formal_oos_allowed"] is False
    assert payload["taxonomy"]["network_attempted"] is False
    assert payload["taxonomy"]["new_attempt_created"] is False
    assert payload["taxonomy"]["formal_credit"] is False
    assert payload["taxonomy"]["rule_scope_compatible"] is False
    assert "capture_attempt_id" not in payload
    assert reuse_calls == ["reuse"]
    assert (status_root / "latest_status.json").is_file()


@pytest.mark.parametrize(
    ("drift", "error"),
    (
        ("denominator", "current split binding differs from candidate"),
        ("rule_score", "current full Rule score/clock tuple differs"),
        ("rule_clock", "current split binding differs from candidate: rule_candidate_binding"),
    ),
)
def test_same_day_reuse_fails_closed_on_denominator_or_rule_tuple_drift(
    drift: str,
    error: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _patch_reuse_candidate(monkeypatch, tmp_path)
    if drift == "denominator":
        monkeypatch.setattr(
            runner,
            "validate_prospective_pit_denominator",
            lambda *_args, **_kwargs: {"symbols": ["2330"]},
        )
    elif drift == "rule_score":
        parent = fixture["parent"]
        assert isinstance(parent, dict)
        parent["scores_bp"] = (8999, 8000)
    else:
        parent = fixture["parent"]
        assert isinstance(parent, dict)
        parent["clock_id"] = "clock:drifted"

    with pytest.raises(runner.PITTaxonomySourceError, match=error):
        runner._reuse_existing_split_taxonomy_candidate(
            publication_root=fixture["publication_root"],  # type: ignore[arg-type]
            observed=OBSERVED,
            config_path=None,
            now_provider=lambda: fixture["validation_completed_at"],  # type: ignore[return-value]
        )
    assert "attempt_config_binding" not in fixture["checked"]


def test_same_day_reuse_rejects_validation_completed_at_cutoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _patch_reuse_candidate(
        monkeypatch,
        tmp_path,
        validation_completed_at=datetime(2026, 10, 1, 8, 30, tzinfo=TAIPEI),
    )
    with pytest.raises(runner.PITTaxonomySourceError, match="validation finished outside Taipei 08:30 cutoff"):
        runner._reuse_existing_split_taxonomy_candidate(
            publication_root=fixture["publication_root"],  # type: ignore[arg-type]
            observed=datetime(2026, 10, 1, 8, 29, 59, tzinfo=TAIPEI),
            config_path=None,
            now_provider=lambda: fixture["validation_completed_at"],  # type: ignore[return-value]
        )


def test_reuse_source_plan_and_current_urls_must_match_attempt_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = runner.load_pit_taxonomy_source_config(
        runner.ROOT / "scripts" / "scheduled" / "pit_taxonomy_source_config.json",
        bounded_read=True,
    )
    company_raw = {"twse": b"twse", "tpex": b"tpex"}
    planned = runner._plan_configured_components(config, company_raw, CAPTURE_DATE)
    urls = runner._config_expected_urls(config)
    attempt = {
        "components": [
            {
                "source_name": item["source_name"],
                "http_metadata": {"requested_url": urls[item["source_name"]]},
            }
            for item in planned
        ]
    }
    descriptor = {"planned_sources": planned}
    runner._verify_reused_attempt_source_config(
        attempt=attempt,
        descriptor=descriptor,
        config=config,
        company_raw=company_raw,
        capture_date=CAPTURE_DATE,
    )

    changed_plan = {**descriptor, "planned_sources": planned[:-1]}
    with pytest.raises(runner.PITTaxonomySourceError, match="source plan differs"):
        runner._verify_reused_attempt_source_config(
            attempt=attempt,
            descriptor=changed_plan,
            config=config,
            company_raw=company_raw,
            capture_date=CAPTURE_DATE,
        )

    changed_attempt = {"components": [dict(item) for item in attempt["components"]]}
    first_component = changed_attempt["components"][0]
    first_component["http_metadata"] = {"requested_url": "https://wrong.example.invalid"}
    with pytest.raises(runner.PITTaxonomySourceError, match="URL differs from source config"):
        runner._verify_reused_attempt_source_config(
            attempt=changed_attempt,
            descriptor=descriptor,
            config=config,
            company_raw=company_raw,
            capture_date=CAPTURE_DATE,
        )
