from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import data_module.formal_daily_input_producer as producer_module
from data_module.formal_daily_input_producer import (
    DailyFormalInputPaths,
    FormalDailyInputProducerError,
    OfficialSourceResponse,
    _load_preopen_pit_candidate,
    _produce_pit_candidate,
    capture_pit_candidate_before_cutoff,
    reuse_pit_candidate_archive_before_cutoff,
    run_daily_formal_input_producer,
)
from data_module.prospective_official_pit_source import (
    OFFICIAL_COMPANY_SOURCE_DEFINITIONS,
)
from scripts.scheduled import run_formal_pit_sidecar_postcutoff as sidecar_runner
from scripts.scheduled import run_pit_sector_membership_preopen_capture as capture_runner


TAIPEI = ZoneInfo("Asia/Taipei")


def test_natural_capture_taxonomy_validation_uses_post_capture_clock_and_nonzero_failure(tmp_path, monkeypatch):
    started = datetime(2026, 9, 30, 7, 0, tzinfo=TAIPEI)
    finished = started + timedelta(seconds=20)

    class Clock(datetime):
        values = iter((started, finished))

        @classmethod
        def now(cls, tz=None):
            return next(cls.values).astimezone(tz)

    monkeypatch.setattr(capture_runner, "datetime", Clock)
    monkeypatch.setattr(capture_runner, "formal_schedule_day_state", lambda **k: (True, "official_open"))
    monkeypatch.setattr(capture_runner, "load_optional_formal_runtime_config", lambda **k: None)
    monkeypatch.setattr(capture_runner, "reuse_pit_candidate_archive_before_cutoff", lambda **k: {
        "durable_archive": {"archive_manifest_path": "archive.json"}, "durable_archive_verified": True,
    })
    monkeypatch.setattr(capture_runner, "_refresh_pit_denominator", lambda **k: {"status": "captured_verified"})

    def taxonomy(**kwargs):
        assert kwargs["observed"] == finished
        assert kwargs["observed"] > started
        return {"status": "blocked", "blockers": ["exact_source_blocker"]}

    monkeypatch.setattr(capture_runner, "_capture_taxonomy_for_run", taxonomy)
    payload, code = capture_runner.run_capture(publication_root=tmp_path, status_root=tmp_path / "status")
    assert code == 2
    assert payload["status"] == "degraded"
    assert payload["archive_readback_verified"] is True
    assert payload["blockers"] == ["exact_source_blocker"]
    assert datetime.fromisoformat(payload["taxonomy_observed_at"]) == finished


def test_postcutoff_history_calendar_cannot_probe_network(tmp_path, monkeypatch):
    calls = []

    def classify(self, target_date, allow_online_probe=True):
        calls.append(allow_online_probe)
        return None, "missing_official_cache"

    monkeypatch.setattr(sidecar_runner.OfficialTradingCalendar, "is_official_trading_day", classify)
    calendar = sidecar_runner._OfflinePITHistoryCalendar(db_path=tmp_path / "market.db")
    assert calendar.is_official_trading_day(date(2026, 9, 29)) == (None, "missing_official_cache")
    assert calls == [False]


def test_scheduled_taxonomy_config_is_live_bounded_and_never_formally_self_accepted():
    from data_module.pit_taxonomy_source_producer import load_pit_taxonomy_source_config

    root = Path(__file__).resolve().parents[1] / "scripts" / "scheduled"
    config = load_pit_taxonomy_source_config(root / "pit_taxonomy_source_config.json")
    assert config["license_scope"]["formal_acceptance_granted"] is False
    assert config["license_scope"]["redistribution_allowed"] is False
    assert config["security"]["all"]["url"] == "https://isin.twse.com.tw/isin/e_single_main.jsp"
    for market in config["classification"].values():
        assert "mapping" not in market
        specs = market.get("components", {"primary": market})
        for source in specs.values():
            assert source["url"].startswith("https://")
            assert "path" not in source and "http" not in source
    cmd = (root / "run_pit_sector_membership_preopen_capture.cmd").read_text(encoding="utf-8")
    assert 'if not defined PIT_TAXONOMY_SOURCE_CONFIG' in cmd
    assert 'pit_taxonomy_source_config.json' in cmd


class _FrozenDateTime(datetime):
    frozen_utc = datetime(2026, 8, 17, 0, 20, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz: object = None) -> _FrozenDateTime:
        if tz is None:
            return cls.fromtimestamp(cls.frozen_utc.timestamp())
        return cls.fromtimestamp(cls.frozen_utc.timestamp(), tz)


def _raw_payloads(publication_date: date) -> dict[str, bytes]:
    twse = [
        {"公司代號": "1101", "產業別": "01", "出表日期": publication_date.strftime("%Y%m%d")},
        {"公司代號": "1102", "產業別": "02", "出表日期": publication_date.strftime("%Y%m%d")},
    ]
    tpex = [
        {
            "SecuritiesCompanyCode": "5501",
            "SecuritiesIndustryCode": "03",
            "Date": publication_date.isoformat(),
        },
        {
            "SecuritiesCompanyCode": "5502",
            "SecuritiesIndustryCode": "05",
            "Date": publication_date.isoformat(),
        },
    ]
    return {
        "twse": json.dumps(twse, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(),
        "tpex": json.dumps(tpex, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(),
    }


def _responses(captured_at: datetime, raw: dict[str, bytes]) -> dict[str, OfficialSourceResponse]:
    return {
        OFFICIAL_COMPANY_SOURCE_DEFINITIONS[market].endpoint: OfficialSourceResponse(
            body=raw[market],
            metadata={
                "requested_url": OFFICIAL_COMPANY_SOURCE_DEFINITIONS[market].endpoint,
                "final_url": OFFICIAL_COMPANY_SOURCE_DEFINITIONS[market].endpoint,
                "http_status": 200,
                "content_type": "application/json",
                "http_date": None,
                "http_last_modified": None,
                "captured_at": captured_at.isoformat(),
            },
        )
        for market in ("twse", "tpex")
    }


def _make_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    captured_at: datetime,
    observed: datetime,
) -> Path:
    monkeypatch.setenv("RULE_CHAMPION_CONTROLLED_STORE_HMAC_KEY", "preopen-test-key")
    monkeypatch.setenv("RULE_CHAMPION_CONTROLLED_STORE_ID", "preopen-test-store")
    _FrozenDateTime.frozen_utc = (
        observed.astimezone(timezone.utc) + timedelta(seconds=10)
    )
    monkeypatch.setattr(producer_module, "datetime", _FrozenDateTime)
    raw = _raw_payloads(captured_at.astimezone(TAIPEI).date() - timedelta(days=1))
    responses = _responses(captured_at, raw)
    paths = DailyFormalInputPaths(
        output_root=tmp_path / "candidate",
        development_output_root=tmp_path / "technical_analysis_development_output",
        market_db=tmp_path / "unused-market.sqlite",
        publication_root=tmp_path / "publication",
    )
    paths.output_root.mkdir()
    result = _produce_pit_candidate(
        paths=paths,
        output_root=paths.output_root,
        observed=_FrozenDateTime.fromtimestamp(
            observed.timestamp(), observed.tzinfo
        ),
        expected_symbols=None,
        fetch_source=lambda url: responses[url],
    )
    archive = result["durable_archive"]
    assert isinstance(archive, dict)
    return Path(str(archive["archive_manifest_path"]))


def test_preopen_capture_rejects_a_started_run_after_cutoff_without_fetch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def should_not_fetch(_url: str) -> OfficialSourceResponse:
        nonlocal called
        called = True
        raise AssertionError("post-cutoff capture must not fetch official source")

    with pytest.raises(FormalDailyInputProducerError, match="only allowed before"):
        capture_pit_candidate_before_cutoff(
            publication_root=tmp_path / "publication",
            candidate_root=tmp_path / "candidate",
            now=datetime(2026, 8, 17, 9, 0, tzinfo=TAIPEI),
            fetch_source=should_not_fetch,
        )
    assert called is False


def test_preopen_public_capture_writes_a_cutoff_bound_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed = datetime(2026, 8, 17, 0, 15, tzinfo=TAIPEI)
    captured = datetime(2026, 8, 17, 0, 10, tzinfo=TAIPEI)
    _FrozenDateTime.frozen_utc = observed.astimezone(timezone.utc)
    monkeypatch.setattr(producer_module, "datetime", _FrozenDateTime)
    raw = _raw_payloads(captured.astimezone(TAIPEI).date() - timedelta(days=1))
    responses = _responses(captured, raw)
    result = capture_pit_candidate_before_cutoff(
        publication_root=tmp_path / "publication",
        candidate_root=tmp_path / "candidate",
        now=_FrozenDateTime.fromtimestamp(observed.timestamp(), TAIPEI),
        fetch_source=lambda url: responses[url],
    )
    assert result["source_lane"] == "preopen_cutoff_machine_capture"
    assert result["captured_before_cutoff"] is True
    assert result["durable_archive_verified"] is True
    archive = result["durable_archive"]
    assert isinstance(archive, dict)
    assert Path(str(archive["archive_manifest_path"])).is_file()


def test_preopen_archive_is_read_after_cutoff_without_same_day_refetch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = datetime(2026, 8, 17, 0, 10, tzinfo=TAIPEI)
    manifest = _make_archive(
        tmp_path,
        monkeypatch,
        captured_at=captured,
        observed=datetime(2026, 8, 17, 0, 15, tzinfo=TAIPEI),
    )
    result = _load_preopen_pit_candidate(
        archive_root=manifest.parents[1].parent,
        observed=_FrozenDateTime.fromtimestamp(
            datetime(2026, 8, 17, 9, 0, tzinfo=TAIPEI).timestamp(),
            TAIPEI,
        ),
    )
    assert result["source_lane"] == "preopen_archive_readback"
    assert result["captured_before_cutoff"] is True
    assert result["post_cutoff_refetch_forbidden"] is True
    assert result["row_count"] == 4
    assert result["durable_archive_verified"] is True


def test_preopen_schedule_reuses_existing_archive_before_cutoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = datetime(2026, 8, 17, 0, 10, tzinfo=TAIPEI)
    observed = datetime(2026, 8, 17, 0, 20, tzinfo=TAIPEI)
    manifest = _make_archive(
        tmp_path,
        monkeypatch,
        captured_at=captured,
        observed=datetime(2026, 8, 17, 0, 15, tzinfo=TAIPEI),
    )

    reused = reuse_pit_candidate_archive_before_cutoff(
        publication_root=manifest.parents[2].parent,
        now=_FrozenDateTime.fromtimestamp(observed.timestamp(), TAIPEI),
    )
    assert reused["source_lane"] == "preopen_archive_reuse"
    assert reused["durable_archive_verified"] is True
    assert reused["archive_selection_reason"] == (
        "reused latest valid immutable archive captured and persisted before "
        "Taipei 08:30; live source refetch was skipped"
    )

    monkeypatch.setattr(
        capture_runner,
        "capture_pit_candidate_before_cutoff",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("a valid current-day archive must be reused")
        ),
    )
    payload, exit_code = capture_runner.run_capture(
        publication_root=manifest.parents[2].parent,
        status_root=manifest.parents[2].parent / "status",
        now=_FrozenDateTime.fromtimestamp(observed.timestamp(), TAIPEI),
    )
    assert exit_code == 0
    assert payload["capture_mode"] == "reused_existing_verified_archive"
    capture = payload["capture"]
    assert isinstance(capture, dict)
    assert capture["source_lane"] == "preopen_archive_reuse"


def test_preopen_schedule_fails_closed_for_invalid_existing_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = datetime(2026, 8, 17, 0, 10, tzinfo=TAIPEI)
    observed = datetime(2026, 8, 17, 0, 20, tzinfo=TAIPEI)
    manifest = _make_archive(
        tmp_path,
        monkeypatch,
        captured_at=captured,
        observed=datetime(2026, 8, 17, 0, 15, tzinfo=TAIPEI),
    )
    publication = manifest.parent / "pit-sector-membership-machine.json"
    publication.write_bytes(publication.read_bytes() + b"tampered")
    live_called = False

    def must_not_hide_tamper(**_kwargs: object) -> dict[str, object]:
        nonlocal live_called
        live_called = True
        raise AssertionError("invalid archive must not trigger a replacement capture")

    monkeypatch.setattr(capture_runner, "capture_pit_candidate_before_cutoff", must_not_hide_tamper)
    payload, exit_code = capture_runner.run_capture(
        publication_root=manifest.parents[2].parent,
        status_root=manifest.parents[2].parent / "status",
        now=_FrozenDateTime.fromtimestamp(observed.timestamp(), TAIPEI),
    )
    assert exit_code == 2
    assert payload["status"] == "blocked"
    assert live_called is False
    blockers = payload.get("blockers")
    assert isinstance(blockers, list)
    assert any("pit_preopen_capture_failed" in str(item) for item in blockers)


def test_preopen_schedule_does_not_replace_partial_archive_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publication_root = tmp_path / "publication"
    partial = publication_root / "pit_candidate_archive" / "2026-08-17" / "run-partial"
    partial.mkdir(parents=True)
    (partial / "pit-sector-membership-machine.json").write_text("partial", encoding="utf-8")
    live_called = False

    def must_not_replace(**_kwargs: object) -> dict[str, object]:
        nonlocal live_called
        live_called = True
        raise AssertionError("a partial archive must remain an observable blocker")

    monkeypatch.setattr(capture_runner, "capture_pit_candidate_before_cutoff", must_not_replace)
    payload, exit_code = capture_runner.run_capture(
        publication_root=publication_root,
        status_root=publication_root / "status",
        now=datetime(2026, 8, 17, 0, 20, tzinfo=TAIPEI),
    )
    assert exit_code == 2
    assert payload["status"] == "blocked"
    assert live_called is False
    blockers = payload.get("blockers")
    assert isinstance(blockers, list)
    assert any("incomplete archive" in str(item) for item in blockers)


def test_postcutoff_consumer_rejects_archive_captured_after_cutoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = datetime(2026, 8, 17, 9, 0, tzinfo=TAIPEI)
    manifest = _make_archive(
        tmp_path,
        monkeypatch,
        captured_at=captured,
        observed=datetime(2026, 8, 17, 9, 5, tzinfo=TAIPEI),
    )
    with pytest.raises(FormalDailyInputProducerError, match="no valid before-cutoff"):
        _load_preopen_pit_candidate(
            archive_root=manifest.parents[1].parent,
            observed=_FrozenDateTime.fromtimestamp(
                datetime(2026, 8, 17, 10, 0, tzinfo=TAIPEI).timestamp(),
                TAIPEI,
            ),
        )


def test_postcutoff_consumer_rejects_archive_persisted_at_or_after_cutoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = datetime(2026, 8, 17, 0, 10, tzinfo=TAIPEI)
    manifest_path = _make_archive(
        tmp_path,
        monkeypatch,
        captured_at=captured,
        observed=datetime(2026, 8, 17, 0, 15, tzinfo=TAIPEI),
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["archived_at"] = datetime(
        2026, 8, 17, 8, 30, tzinfo=TAIPEI
    ).isoformat()
    body = dict(payload)
    body.pop("manifest_hash", None)
    payload["manifest_hash"] = producer_module._payload_hash(body)
    manifest_path.write_bytes(
        (producer_module._canonical_json(payload) + "\n").encode("utf-8")
    )
    with pytest.raises(FormalDailyInputProducerError, match="persistence is not before"):
        _load_preopen_pit_candidate(
            archive_root=manifest_path.parents[1].parent,
            observed=_FrozenDateTime.fromtimestamp(
                datetime(2026, 8, 17, 10, 0, tzinfo=TAIPEI).timestamp(),
                TAIPEI,
            ),
        )


def test_formal_daily_runner_uses_archive_mode_without_pit_refetch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RULE_CHAMPION_CONTROLLED_STORE_HMAC_KEY", "preopen-test-key")
    monkeypatch.setenv("RULE_CHAMPION_CONTROLLED_STORE_ID", "preopen-test-store")
    sentinel = {
        "status": "machine_verified_candidate",
        "source_lane": "preopen_archive_readback",
        "candidate_only": True,
        "formal_consumer_compatible": False,
        "consumer_verified": True,
    }
    monkeypatch.setattr(
        producer_module,
        "_load_preopen_pit_candidate",
        lambda **_kwargs: dict(sentinel),
    )

    def must_not_refetch(**_kwargs: object) -> dict[str, object]:
        raise AssertionError("archive mode must not call the live PIT producer")

    monkeypatch.setattr(producer_module, "_produce_pit_candidate", must_not_refetch)
    paths = DailyFormalInputPaths(
        output_root=tmp_path / "candidate",
        development_output_root=tmp_path / "technical_analysis_development_output",
        market_db=tmp_path / "missing.sqlite",
        publication_root=None,
        pit_preopen_archive_root=tmp_path / "archive",
    )
    result = run_daily_formal_input_producer(
        paths,
        now=datetime(2026, 8, 17, 9, 0, tzinfo=TAIPEI),
        calendar=None,
    )
    inputs = result["inputs"]
    assert isinstance(inputs, dict)
    pit = inputs["pit_candidate"]
    assert isinstance(pit, dict)
    assert pit["source_lane"] == "preopen_archive_readback"


def test_preopen_scheduled_status_records_archive_and_fail_closed_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        capture_runner,
        "capture_pit_candidate_before_cutoff",
        lambda **_kwargs: {
            "status": "machine_verified_candidate",
            "durable_archive": {
                "archive_manifest_path": str(tmp_path / "archive_manifest.json")
            },
            "durable_archive_verified": True,
        },
    )
    payload, exit_code = capture_runner.run_capture(
        publication_root=tmp_path / "publication",
        status_root=tmp_path / "publication" / "status",
        now=datetime(2026, 8, 17, 0, 10, tzinfo=TAIPEI),
    )
    assert exit_code == 0
    assert payload["status"] == "machine_verified_candidate"
    assert payload["archive_readback_verified"] is True
    assert payload["post_cutoff_refetch_forbidden"] is True


def test_split_preopen_status_keeps_stable_latest_path_for_default_caller(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed = datetime(2026, 8, 17, 0, 10, tzinfo=TAIPEI)
    monkeypatch.setattr(
        capture_runner,
        "formal_schedule_day_state",
        lambda **_kwargs: (True, "official_open"),
    )
    monkeypatch.setattr(
        capture_runner,
        "load_optional_formal_runtime_config",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        capture_runner,
        "reuse_pit_candidate_archive_before_cutoff",
        lambda **_kwargs: {
            "status": "machine_verified_candidate",
            "durable_archive": {"archive_manifest_path": str(tmp_path / "archive.json")},
            "durable_archive_verified": True,
        },
    )
    monkeypatch.setattr(
        capture_runner,
        "_refresh_pit_denominator",
        lambda **_kwargs: {"status": "existing_verified", "network_attempted": False},
    )
    monkeypatch.setattr(
        capture_runner,
        "_capture_taxonomy_for_run",
        lambda **_kwargs: {"status": "preopen_captured", "blockers": []},
    )
    status_root = tmp_path / "operational-status"

    payload, exit_code = capture_runner.run_capture(
        publication_root=tmp_path / "publication",
        status_root=status_root,
        now=observed,
        split_denominator_contract=True,
    )

    expected_status_path = status_root / "latest_status.json"
    assert exit_code == 0
    assert payload["capture_attempt_id"]
    assert payload["status_path"] == str(expected_status_path)
    assert expected_status_path.is_file()
    persisted = json.loads(expected_status_path.read_text(encoding="utf-8"))
    assert persisted["capture_attempt_id"] == payload["capture_attempt_id"]


def _make_split_scope_binding_inputs(tmp_path: Path) -> tuple[
    Path,
    Path,
    dict[str, object],
    dict[str, object],
]:
    publication_root = tmp_path / "publication"
    rule_root = publication_root / "rule_source" / "clock-20260817-fixture"
    identity_path = rule_root / "metadata" / "universe_identity.json"
    symbols_path = rule_root / "metadata" / "universe_symbols.json"
    clock_path = rule_root / "clock" / "manifest.json"
    source_window_path = rule_root / "source" / "daily_price_window.json"
    denominator_path = (
        publication_root
        / "pit_denominator"
        / "2026-08-17-run-fixture"
        / "denominator.json"
    )
    for path in (identity_path, symbols_path, clock_path, source_window_path, denominator_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    source_window_payload = {
        "schema_version": "manual-rule-only-daily-price-window.v1",
        "source_id": "daily_prices",
        "decision_session": "2026-08-17",
    }
    source_window_hash = capture_runner._sha256_json(source_window_payload)
    source_window = {
        "schema_version": "formal-rule-source-window.v1",
        "source_window_hash": source_window_hash,
        "source_payload": source_window_payload,
    }
    source_window_raw = capture_runner.canonical_json(source_window).encode("utf-8")
    identity: dict[str, object] = {
        "source_window_hash": source_window_hash,
        "source_window_file_hash": capture_runner._sha256_bytes(source_window_raw),
    }
    clock = {"clock_id": "clock:fixture", "manifest_hash": "sha256:fixture-clock"}
    symbols = ["1101"]
    denominator: dict[str, object] = {
        "symbols": symbols,
        "content_sha256": "sha256:fixture-denominator-content",
        "symbols_hash": capture_runner._sha256_json(symbols),
        "scope": "prospective_pit_sector_membership",
        "coverage_start": "2026-08-17",
        "observed_at": "2026-08-16T23:20:00+00:00",
    }
    for path, payload in (
        (identity_path, identity),
        (symbols_path, symbols),
        (clock_path, clock),
        (source_window_path, source_window),
        (denominator_path, denominator),
    ):
        path.write_bytes(capture_runner.canonical_json(payload).encode("utf-8"))

    parent: dict[str, object] = {
        "bundle_root": str(rule_root),
        "identity_path": str(identity_path),
        "symbols_path": str(symbols_path),
        "clock_path": str(clock_path),
        "identity": identity,
        "symbols_payload": symbols,
        "clock": clock,
        "expected_symbols": ("1101",),
        "universe_hash_symbols": ("1101",),
        "scores_bp": (9000,),
        "rank_order": ("1101",),
        "rank_order_source": "parent.universe_hash_symbols",
        "universe_hash": "sha256:fixture-universe",
        "clock_id": "clock:fixture",
        "clock_manifest_hash": "sha256:fixture-clock",
    }
    return publication_root, denominator_path, denominator, parent


def test_split_scope_binding_uses_bounded_confined_source_bytes_once(tmp_path: Path) -> None:
    publication_root, denominator_path, denominator, parent = _make_split_scope_binding_inputs(tmp_path)

    binding = capture_runner._build_split_scope_binding(
        publication_root=publication_root,
        denominator_path=denominator_path,
        denominator_payload=denominator,
        parent=parent,  # type: ignore[arg-type]
        capture_date=date(2026, 8, 17),
        decision_at=datetime(2026, 8, 17, 8, 30, tzinfo=TAIPEI),
        denominator_symbols=("1101",),
    )

    assert binding["taxonomy_coverage_complete"] is True
    assert binding["rule_scope_compatible"] is True
    denom_binding = binding["denominator_binding"]
    rule_binding = binding["rule_candidate_binding"]
    assert isinstance(denom_binding, dict)
    assert denom_binding["file_sha256"] == capture_runner._sha256_bytes(
        denominator_path.read_bytes()
    )
    assert isinstance(rule_binding, dict)
    assert set(rule_binding["file_hashes"]) == {
        "identity",
        "symbols",
        "clock",
        "source_window",
    }


def test_split_scope_binding_rejects_oversized_source_before_hashing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publication_root, denominator_path, denominator, parent = _make_split_scope_binding_inputs(tmp_path)
    monkeypatch.setattr(capture_runner, "SPLIT_RULE_METADATA_PROOF_MAX_BYTES", 8)

    with pytest.raises(capture_runner.PITTaxonomySourceError, match="proof file custody failed"):
        capture_runner._build_split_scope_binding(
            publication_root=publication_root,
            denominator_path=denominator_path,
            denominator_payload=denominator,
            parent=parent,  # type: ignore[arg-type]
            capture_date=date(2026, 8, 17),
            decision_at=datetime(2026, 8, 17, 8, 30, tzinfo=TAIPEI),
            denominator_symbols=("1101",),
        )


def test_split_scope_binding_rejects_linked_proof_path(tmp_path: Path) -> None:
    publication_root, denominator_path, denominator, parent = _make_split_scope_binding_inputs(tmp_path)
    identity_path = Path(str(parent["identity_path"]))
    identity_path.unlink()
    outside = tmp_path / "outside_identity.json"
    outside.write_text("{}", encoding="utf-8")
    try:
        identity_path.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"Windows symlink privilege unavailable: {error}")

    with pytest.raises(capture_runner.PITTaxonomySourceError, match="contains a link"):
        capture_runner._build_split_scope_binding(
            publication_root=publication_root,
            denominator_path=denominator_path,
            denominator_payload=denominator,
            parent=parent,  # type: ignore[arg-type]
            capture_date=date(2026, 8, 17),
            decision_at=datetime(2026, 8, 17, 8, 30, tzinfo=TAIPEI),
            denominator_symbols=("1101",),
        )


def test_split_scope_binding_rejects_parent_fingerprint_mutation(tmp_path: Path) -> None:
    publication_root, denominator_path, denominator, parent = _make_split_scope_binding_inputs(tmp_path)
    symbols_path = Path(str(parent["symbols_path"]))
    symbols_path.write_text('["2330"]', encoding="utf-8")

    with pytest.raises(capture_runner.PITTaxonomySourceError, match="symbols bytes changed"):
        capture_runner._build_split_scope_binding(
            publication_root=publication_root,
            denominator_path=denominator_path,
            denominator_payload=denominator,
            parent=parent,  # type: ignore[arg-type]
            capture_date=date(2026, 8, 17),
            decision_at=datetime(2026, 8, 17, 8, 30, tzinfo=TAIPEI),
            denominator_symbols=("1101",),
        )


def test_split_scope_binding_rejects_denominator_fingerprint_mutation(tmp_path: Path) -> None:
    publication_root, denominator_path, denominator, parent = _make_split_scope_binding_inputs(tmp_path)
    denominator_path.write_text('{"symbols": ["2330"]}', encoding="utf-8")

    with pytest.raises(capture_runner.PITTaxonomySourceError, match="denominator bytes differ"):
        capture_runner._build_split_scope_binding(
            publication_root=publication_root,
            denominator_path=denominator_path,
            denominator_payload=denominator,
            parent=parent,  # type: ignore[arg-type]
            capture_date=date(2026, 8, 17),
            decision_at=datetime(2026, 8, 17, 8, 30, tzinfo=TAIPEI),
            denominator_symbols=("1101",),
        )


def test_preopen_refresh_reuses_verified_same_day_denominator_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publication_root = tmp_path / "publication"
    denominator = (
        publication_root
        / "pit_denominator"
        / "2026-08-17-run-existing"
        / "denominator.json"
    )
    denominator.parent.mkdir(parents=True)
    denominator.write_text("{}", encoding="utf-8")
    calls: list[Path] = []

    def validate(path: Path, *, now: datetime | None = None) -> dict[str, object]:
        del now
        calls.append(path)
        return {"coverage_start": "2026-08-17"}

    monkeypatch.setattr(capture_runner, "validate_prospective_pit_denominator", validate)
    monkeypatch.setattr(
        capture_runner,
        "capture_live_denominator",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("verified denominator should be reused")
        ),
    )

    result = capture_runner._refresh_pit_denominator(
        publication_root=publication_root,
        observed=datetime(2026, 8, 17, 0, 10, tzinfo=TAIPEI),
        allow_network=True,
    )

    assert result["status"] == "existing_verified"
    assert result["network_attempted"] is False
    assert calls == [denominator.resolve()]


def test_preopen_refresh_captures_missing_denominator_in_repo_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publication_root = tmp_path / "publication"
    captured: dict[str, object] = {}

    def fake_capture(*, output_dir: Path, coverage_start: date) -> dict[str, object]:
        captured.update({"output_dir": output_dir, "coverage_start": coverage_start})
        output_dir.mkdir(parents=True)
        path = output_dir / "denominator.json"
        path.write_text("{}", encoding="utf-8")
        return {"path": str(path), "file_sha256": "sha256:" + "a" * 64}

    monkeypatch.setattr(capture_runner, "capture_live_denominator", fake_capture)
    monkeypatch.setattr(
        capture_runner,
        "validate_prospective_pit_denominator",
        lambda _path, **_kwargs: {
            "coverage_start": "2026-08-17",
            "content_sha256": "sha256:" + "b" * 64,
            "symbol_count": 1984,
            "license_scope": {"status": "machine_scope_verified"},
        },
    )

    result = capture_runner._refresh_pit_denominator(
        publication_root=publication_root,
        observed=datetime(2026, 8, 17, 0, 10, tzinfo=TAIPEI),
        allow_network=True,
    )

    assert result["status"] == "captured_verified"
    assert result["network_attempted"] is True
    output_dir = captured["output_dir"]
    assert isinstance(output_dir, Path)
    assert output_dir.parent == publication_root / "pit_denominator"
    assert captured["coverage_start"] == date(2026, 8, 17)
    assert result["path"] == str((output_dir / "denominator.json").resolve())


def test_sidecar_scheduled_runner_waits_for_natural_cutoff(
    tmp_path: Path,
) -> None:
    payload, exit_code = sidecar_runner.run_sidecar(
        publication_root=tmp_path / "publication",
        status_root=tmp_path / "publication" / "status",
        now=datetime(2026, 8, 17, 8, 29, 59, tzinfo=TAIPEI),
    )
    assert exit_code == 2
    assert payload["status"] == "waiting_for_taipei_cutoff"
    assert payload["same_day_post_cutoff_http_refetch"] is False


def test_pit_schedule_wrappers_encode_safe_pacific_to_taipei_windows() -> None:
    scheduled = Path(__file__).resolve().parents[1] / "scripts" / "scheduled"
    capture_cmd = (scheduled / "run_pit_sector_membership_preopen_capture.cmd").read_text(
        encoding="utf-8"
    )
    sidecar_cmd = (scheduled / "run_formal_pit_sidecar_postcutoff.cmd").read_text(
        encoding="utf-8"
    )
    paper_capture_cmd = (
        scheduled / "run_paper_event_source_capture_daily.cmd"
    ).read_text(encoding="utf-8")
    formal_cmd = (scheduled / "run_formal_input_producer_daily.cmd").read_text(
        encoding="utf-8"
    )
    register_cmd = (scheduled / "register_pit_sector_handoff_tasks.cmd").read_text(
        encoding="utf-8"
    )
    assert "run_pit_sector_membership_preopen_capture.py" in capture_cmd
    assert "run_formal_pit_sidecar_postcutoff.py" in sidecar_cmd
    assert "run_paper_event_source_capture_daily.py" in sidecar_cmd
    assert "run_paper_event_source_capture_daily.py" in paper_capture_cmd
    assert "--now" not in capture_cmd + sidecar_cmd
    assert "FORMAL_DAILY_PIT_PREOPEN_ARCHIVE_ROOT" in formal_cmd
    assert "baldr-pit-sector-membership-preopen-capture-daily" in register_cmd
    assert "baldr-formal-pit-sidecar-postcutoff-daily" in register_cmd
    assert "16:00" in register_cmd and "18:00" in register_cmd
    assert "07:00 PDT / 08:00 PST" in register_cmd
    assert "09:00 PDT / 10:00 PST" in register_cmd
    assert "dryrun" in register_cmd and "register" in register_cmd
