from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app_module.recommendation.current_market_status_preflight import (
    CURRENT_MARKET_STATUS_POINTER_RELATIVE,
    CurrentMarketStatusPreflight,
    validate_current_market_status_evidence,
)
from app_module.recommendation.input_preparation import (
    RecommendationInputSession,
    build_default_recommendation_input_preparer,
)
from data_module.current_market_status_observation import (
    MarketStatusEvidence,
    build_snapshot,
)


def write_4130_pointer_fixture(
    source_root: Path,
    *,
    effective_from: str = "2026-07-28",
    published_date: str | None = "2026-07-27",
    captured_at: datetime = datetime(2026, 10, 4, 12, 40, 1, tzinfo=timezone.utc),
    snapshot_observed_at: datetime = datetime(2026, 10, 4, 12, 40, 4, tzinfo=timezone.utc),
    capture_final_url: str = "https://www.tpex.org.tw/www/zh-tw/company/deListed",
    capture_status: str = "captured",
    parse_status: str = "parsed",
    http_status: int = 200,
    partial_failure: bool = False,
) -> dict[str, Path | str]:
    """Write one isolated, fully pinned official 4130 current-status fixture.

    This helper is intentionally public so the recommendation-service owner
    can exercise the public service path without reading the production data
    root or contacting the network.
    """

    import hashlib as _hashlib

    from data_module.current_market_status_observation import sha256_bytes

    resolved_root = source_root.resolve()
    pointer_path = resolved_root / CURRENT_MARKET_STATUS_POINTER_RELATIVE
    output_dir = pointer_path.parent
    run_id = "fixture-4130-20261004"
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = run_dir / "raw"
    raw_dir.mkdir()
    raw_path = raw_dir / "s0001.bin"
    raw_body = b"Fixture bytes representing the official TPEx termination capture.\n"
    raw_path.write_bytes(raw_body)
    raw_sha256 = "sha256:" + _hashlib.sha256(raw_body).hexdigest()
    source_id = "tpex.terminated_listing"
    source_url = "https://www.tpex.org.tw/www/zh-tw/company/deListed"
    captured_text = captured_at.astimezone(timezone.utc).isoformat(timespec="microseconds")
    capture: dict[str, object] = {
        "source_id": source_id,
        "url": source_url,
        "final_url": capture_final_url,
        "status": capture_status,
        "parse_status": parse_status,
        "http_status": http_status,
        "captured_at": captured_text,
        "raw_path": str(raw_path),
        "raw_sha256": raw_sha256,
        "raw_bytes": len(raw_body),
    }
    evidence = MarketStatusEvidence(
        symbol="4130",
        source_id=source_id,
        evidence_type="terminated",
        observed_at=captured_text,
        raw_sha256=raw_sha256,
        source_url=source_url,
        effective_from=effective_from,
        published_date=published_date,
        notice_reference="櫃買中心11500054131號",
        market="tpex",
        name="東浦精密",
    )
    snapshot = build_snapshot(
        observed_at=snapshot_observed_at,
        source_captures=[capture],
        evidence=[evidence],
    )
    snapshot["run_id"] = run_id
    snapshot["source_count"] = 1
    snapshot["successful_source_count"] = int(capture_status == "captured" and parse_status == "parsed")
    snapshot["partial_failure"] = partial_failure
    snapshot_path = run_dir / "snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    snapshot_sha256 = "sha256:" + hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
    manifest_path = run_dir / "manifest.json"
    manifest = {
        "schema_version": "current-market-status-capture-manifest.v1",
        "run_id": run_id,
        "snapshot_path": str(snapshot_path),
        "snapshot_sha256": snapshot_sha256,
        "raw_sources": [
            {
                "source_id": source_id,
                "raw_path": str(raw_path),
                "raw_sha256": raw_sha256,
                "captured_at": captured_text,
                "status": capture_status,
                "parse_status": parse_status,
            }
        ],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    manifest_sha256 = "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    pointer = {
        "schema_version": "current-market-status-pointer.v1",
        "scope": "current_only",
        "pit_eligible": False,
        "run_id": run_id,
        "published_at": snapshot_observed_at.astimezone(timezone.utc).isoformat(),
        "snapshot_path": f"{run_id}/snapshot.json",
        "snapshot_sha256": snapshot_sha256,
        "manifest_path": f"{run_id}/manifest.json",
        "manifest_sha256": manifest_sha256,
        "source_count": 1,
        "successful_source_count": snapshot["successful_source_count"],
        "partial_failure": partial_failure,
    }
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    pointer_path.write_text(json.dumps(pointer, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "source_root": resolved_root,
        "pointer_path": pointer_path,
        "snapshot_path": snapshot_path,
        "manifest_path": manifest_path,
        "raw_path": raw_path,
        "run_id": run_id,
        "raw_sha256": raw_sha256,
    }


_INVOCATION = datetime(2026, 10, 4, 13, 0, tzinfo=timezone.utc)
_DECISION_DATE = date(2026, 10, 4)


def test_official_4130_delisting_requires_bound_raw_capture_and_keeps_current_only_scope(
    tmp_path: Path,
) -> None:
    write_4130_pointer_fixture(tmp_path / "canonical")
    provider = CurrentMarketStatusPreflight(tmp_path / "canonical")

    result = provider.get("4130", cutoff_at=_INVOCATION, decision_date=_DECISION_DATE)

    assert result.disposition == "verified_delisted"
    assert result.reason_code == "official_delisted"
    assert result.evidence is not None
    assert result.evidence["effective_date"] == "2026-07-28"
    assert result.evidence["decision_date"] == "2026-10-04"
    assert result.evidence["scope"] == "current_only"
    assert result.evidence["pit_eligible"] is False
    assert result.evidence["source_http_status"] == 200
    assert validate_current_market_status_evidence(
        result.evidence,
        expected_symbol="4130",
        decision_at=_INVOCATION,
    )


def test_other_source_partial_failure_does_not_discard_a_verified_termination_capture(
    tmp_path: Path,
) -> None:
    write_4130_pointer_fixture(tmp_path / "canonical", partial_failure=True)

    result = CurrentMarketStatusPreflight(tmp_path / "canonical").get(
        "4130", cutoff_at=_INVOCATION, decision_date=_DECISION_DATE
    )

    assert result.disposition == "verified_delisted"
    assert result.evidence is not None
    assert result.evidence["snapshot_partial_failure"] is True


def test_missing_or_mismatched_official_capture_never_excludes(tmp_path: Path) -> None:
    write_4130_pointer_fixture(
        tmp_path / "bad-capture",
        capture_final_url="https://www.tpex.org.tw/not-the-notice",
    )
    mismatch = CurrentMarketStatusPreflight(tmp_path / "bad-capture").get(
        "4130", cutoff_at=_INVOCATION, decision_date=_DECISION_DATE
    )
    assert mismatch.disposition == "unavailable"
    assert mismatch.reason_code == "current_market_status_termination_evidence_unverified"

    info = write_4130_pointer_fixture(tmp_path / "tampered-raw")
    Path(info["raw_path"]).write_bytes(b"changed official raw body")
    tampered = CurrentMarketStatusPreflight(tmp_path / "tampered-raw").get(
        "4130", cutoff_at=_INVOCATION, decision_date=_DECISION_DATE
    )
    assert tampered.disposition == "unavailable"
    assert tampered.reason_code.startswith("current_market_status_pointer_invalid:")


def test_pointer_read_is_bounded(tmp_path: Path) -> None:
    fixture = write_4130_pointer_fixture(tmp_path / "oversized")
    Path(fixture["pointer_path"]).write_bytes(b" " * (1024 * 1024 + 1))

    result = CurrentMarketStatusPreflight(Path(fixture["source_root"])).get(
        "4130", cutoff_at=_INVOCATION, decision_date=_DECISION_DATE
    )

    assert result.disposition == "unavailable"
    assert result.reason_code.startswith("current_market_status_pointer_invalid:")


def test_future_snapshot_or_effective_date_cannot_be_used_for_current_exclusion(
    tmp_path: Path,
) -> None:
    write_4130_pointer_fixture(
        tmp_path / "future-snapshot",
        snapshot_observed_at=datetime(2026, 10, 4, 13, 1, tzinfo=timezone.utc),
    )
    future_snapshot = CurrentMarketStatusPreflight(tmp_path / "future-snapshot").get(
        "4130", cutoff_at=_INVOCATION, decision_date=_DECISION_DATE
    )
    assert future_snapshot.disposition == "unavailable"
    assert future_snapshot.reason_code == "current_market_status_snapshot_after_decision"

    write_4130_pointer_fixture(tmp_path / "future-effective", effective_from="2026-10-05")
    future_effective = CurrentMarketStatusPreflight(tmp_path / "future-effective").get(
        "4130", cutoff_at=_INVOCATION, decision_date=_DECISION_DATE
    )
    assert future_effective.disposition == "unavailable"


def test_evidence_validator_rejects_wrong_symbol_clock_and_changed_digest(tmp_path: Path) -> None:
    fixture = write_4130_pointer_fixture(tmp_path / "canonical")
    result = CurrentMarketStatusPreflight(tmp_path / "canonical").get(
        "4130", cutoff_at=_INVOCATION, decision_date=_DECISION_DATE
    )
    assert result.evidence is not None
    assert not validate_current_market_status_evidence(result.evidence, expected_symbol="5371")
    assert not validate_current_market_status_evidence(
        result.evidence,
        expected_symbol="4130",
        decision_at=datetime(2026, 10, 4, 13, 1, tzinfo=timezone.utc),
    )
    changed = dict(result.evidence)
    changed["raw_sha256"] = "sha256:" + ("0" * 64)
    assert not validate_current_market_status_evidence(changed, expected_symbol="4130")
    changed = dict(result.evidence)
    changed["pit_eligible"] = 0
    assert not validate_current_market_status_evidence(changed, expected_symbol="4130")

    for field in ("pointer_sha256", "snapshot_sha256", "manifest_sha256"):
        changed = dict(result.evidence)
        changed[field] = "sha256:" + ("1" * 64)
        assert not validate_current_market_status_evidence(changed, expected_symbol="4130")
    changed = dict(result.evidence)
    changed["pointer_payload_json"] = str(changed["pointer_payload_json"]) + " "
    assert not validate_current_market_status_evidence(changed, expected_symbol="4130")
    changed = dict(result.evidence)
    changed["snapshot_path"] = str(Path(fixture["snapshot_path"]).parent.parent / "elsewhere" / "snapshot.json")
    assert not validate_current_market_status_evidence(changed, expected_symbol="4130")

    # The fixed pointer may later move; this saved decision still validates
    # against its own exact immutable run and embedded original pointer bytes.
    pointer_path = Path(fixture["pointer_path"])
    pointer_path.write_text("{}\n", encoding="utf-8")
    assert validate_current_market_status_evidence(result.evidence, expected_symbol="4130")


def test_input_session_uses_canonical_status_root_and_never_reads_it_for_historical_scope(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    canonical_root = tmp_path / "canonical"
    shadow_root = tmp_path / "shadow-artifacts"
    write_4130_pointer_fixture(canonical_root)
    config = SimpleNamespace(
        output_root=shadow_root,
        db_file=tmp_path / "missing.sqlite",
        pit_market_scope=None,
    )
    preparer = build_default_recommendation_input_preparer(
        config,
        market_session_cadence_factory=lambda *_args, **_kwargs: None,
        current_fundamental_source_root=canonical_root,
    )
    assert preparer.current_market_status_source_root == canonical_root
    assert preparer.current_fundamental_provider is not None
    assert preparer.current_fundamental_provider.output_root == canonical_root
    live_session = preparer.begin(config, invocation_frozen_at=_INVOCATION)
    assert type(live_session) is RecommendationInputSession
    live_session.resolve_cutoff(
        runtime_config={},
        as_of_date=None,
        historical_research=False,
        select_latest_available_cutoff=False,
    )
    live_result = live_session.get_current_market_status(
        "4130", cutoff_at=_INVOCATION, decision_date=_DECISION_DATE
    )
    assert live_result.disposition == "verified_delisted"

    historical_session = preparer.begin(config, invocation_frozen_at=_INVOCATION)
    historical_session.resolve_cutoff(
        runtime_config={"as_of_date": "2026-10-02"},
        as_of_date="2026-10-02",
        historical_research=True,
        select_latest_available_cutoff=False,
    )
    historical_result = historical_session.get_current_market_status(
        "4130", cutoff_at=_INVOCATION, decision_date=_DECISION_DATE
    )
    assert historical_result.disposition == "unavailable"
    assert historical_result.reason_code == "current_market_status_not_live_scope"


def test_input_session_caches_pointer_reader_per_invocation_and_does_not_read_select_latest(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    canonical_root = tmp_path / "canonical"
    write_4130_pointer_fixture(canonical_root)
    config = SimpleNamespace(
        output_root=tmp_path / "shadow",
        db_file=tmp_path / "missing.sqlite",
        pit_market_scope=None,
    )
    preparer = build_default_recommendation_input_preparer(
        config,
        market_session_cadence_factory=lambda *_args, **_kwargs: None,
        current_fundamental_source_root=canonical_root,
    )
    from data_module.current_market_status_observation import CurrentMarketStatusReader

    original = CurrentMarketStatusReader.from_pointer.__func__
    calls = 0

    def counted(cls, pointer_path):
        nonlocal calls
        calls += 1
        return original(cls, pointer_path)

    monkeypatch.setattr(CurrentMarketStatusReader, "from_pointer", classmethod(counted))
    live_session = preparer.begin(config, invocation_frozen_at=_INVOCATION)
    live_session.resolve_cutoff(
        runtime_config={},
        as_of_date=None,
        historical_research=False,
        select_latest_available_cutoff=False,
    )
    assert live_session.get_current_market_status(
        "4130", cutoff_at=_INVOCATION, decision_date=_DECISION_DATE
    ).disposition == "verified_delisted"
    assert live_session.get_current_market_status(
        "4130", cutoff_at=_INVOCATION, decision_date=_DECISION_DATE
    ).disposition == "verified_delisted"
    assert calls == 1

    latest_session = preparer.begin(config, invocation_frozen_at=_INVOCATION)
    latest_session.resolve_cutoff(
        runtime_config={},
        as_of_date=None,
        historical_research=False,
        select_latest_available_cutoff=True,
    )
    latest = latest_session.get_current_market_status(
        "4130", cutoff_at=_INVOCATION, decision_date=_DECISION_DATE
    )
    assert latest.disposition == "unavailable"
    assert latest.reason_code == "current_market_status_not_live_scope"
    assert calls == 1
