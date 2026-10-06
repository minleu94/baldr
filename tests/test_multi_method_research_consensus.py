"""UX10 的三態、同源、去重與有界唯讀 adapter 驗證。"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
from pathlib import Path

import pytest

from app_module.daily_market_snapshot_repository import (
    DailyMarketSnapshotRepository, DailyMarketSnapshotVerificationError,
    snapshot_artifact_relpath, snapshot_manifest_relpath,
)
from app_module.multi_method_research_consensus import (
    ConsensusContractError, MethodObservation, adapt_daily_market_snapshot,
    build_multi_method_consensus, read_daily_market_consensus,
)
from tests.test_daily_market_snapshot_repository import (
    DECISION_DATE, PUBLISHED_AT, _publish, _snapshot_payload,
)


def _sources(tmp_path: Path):
    pin, _ = _publish(tmp_path, {"2382": _snapshot_payload("2382"),
                               "3034": _snapshot_payload("3034", technical=False)}, ("2382", "3034"))
    snapshot = DailyMarketSnapshotRepository(tmp_path).load_manifest(pin, "ux19-test-cohort", DECISION_DATE)
    return adapt_daily_market_snapshot(snapshot, as_of=PUBLISHED_AT), snapshot


def _reject(code, operation):
    with pytest.raises(ConsensusContractError) as error:
        operation()
    assert error.value.code == code


def test_readonly_pinned_existing_fixture_full_denominator(tmp_path):
    sources, snapshot = _sources(tmp_path)
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob("*.json")}
    model = read_daily_market_consensus(DailyMarketSnapshotRepository(tmp_path),
        manifest_sha256=snapshot.manifest_sha256, cohort_id=snapshot.cohort_id,
        decision_date=DECISION_DATE, as_of=PUBLISHED_AT)
    assert model.denominator == 2
    assert model.sources == sources
    first, second = model.rows
    assert first.stock_code == "2382"
    assert first.selected_method_ids == ("daily_market.close_above_ma20",)
    assert first.selected_family_count == 1
    assert first.all_methods_state == "not_selected"
    assert second.all_methods_state == "unknown"
    assert second.selected_method_count == 0
    assert all(r.multi_family_state == "unknown" for r in model.rows)
    assert model.method_counts == (("daily_market.close_above_ma20", 1, 0, 1),
                                   ("daily_market.close_above_ma60", 0, 1, 1))
    assert model.population_count is None
    assert model.historical_pit_eligible is False and model.research_only is True
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob("*.json")} == before
    json.dumps(model.to_dict(), ensure_ascii=False)


def test_same_stock_and_same_run_replay_dedup_same_family(tmp_path):
    sources, _ = _sources(tmp_path)
    a, b = sources
    bobs = replace(b.observations[0], state="selected", reason="符合 MA60。", unknown_reason="", relation="above")
    b = replace(b, observations=(bobs, b.observations[1]))
    repeated = replace(a, observations=(*a.observations, a.observations[0]))
    model = build_multi_method_consensus((repeated, b, a, b))
    assert model == build_multi_method_consensus((b, a))
    row = model.rows[0]
    assert row.selected_method_count == 2 and row.selected_family_count == 1
    assert row.all_methods_state == "selected" and row.multi_family_state == "unknown"
    assert len(model.sources) == 2 and len(model.rows) == 2


def test_conflicting_duplicate_stock_rejected(tmp_path):
    sources, _ = _sources(tmp_path)
    a = sources[0]
    conflict = replace(a.observations[0], state="not_selected", reason="改版條件。", relation="below")
    _reject("duplicate_stock_revision", lambda: build_multi_method_consensus((replace(a, observations=(*a.observations, conflict)),)))


@pytest.mark.parametrize("field,value", [
    ("snapshot_sha256", "b" * 64), ("snapshot_id", "b" * 64),
    ("cohort_id", "other"), ("cohort_sha256", "b" * 64),
    ("published_at", (PUBLISHED_AT + timedelta(minutes=1)).isoformat()),
])
def test_cross_method_mixed_scope_or_revision_rejected(tmp_path, field, value):
    sources, _ = _sources(tmp_path)
    _reject("cohort_identity_mismatch" if field in {"cohort_id", "cohort_sha256"} else "incomparable_source_scope_or_revision", lambda: build_multi_method_consensus((sources[0], replace(sources[1], **{field: value}))))


def test_same_method_revision_replay_rejected(tmp_path):
    sources, _ = _sources(tmp_path)
    _reject("same_method_source_revision", lambda: build_multi_method_consensus((sources[0], replace(sources[0], snapshot_sha256="b" * 64))))


@pytest.mark.parametrize("field,value,code", [
    ("version", "2.0.0", "method_version_or_contract_mismatch"),
    ("family", "independent", "method_version_or_contract_mismatch"),
    ("method_key", "ranking", "method_not_supported"),
    ("contracts_sha256", "b" * 64, "method_version_or_contract_mismatch"),
    ("snapshot_sha256", "", "source_hash_missing"),
    ("declared_stock_codes", ("2382", "2382"), "denominator_duplicate_or_order"),
    ("declared_stock_codes", tuple(str(1000 + i) for i in range(17)), "denominator_limit"),
    ("observations", (), None),
    ("historical_pit_eligible", True, "unsupported_qualification"),
    ("universe_sha256", "b" * 64, "universe_hash_mismatch"),
    ("population_count", 3, "population_count_mismatch"),
])
def test_source_contracts_and_missing_method_preserve_unknown(tmp_path, field, value, code):
    sources, _ = _sources(tmp_path)
    mutated = replace(sources[0], **{field: value})
    if code:
        _reject(code, lambda: build_multi_method_consensus((mutated, sources[1])))
    else:
        model = build_multi_method_consensus((mutated, sources[1]))
        assert model.method_counts[0] == (sources[0].method_id, 0, 0, 2)
        assert all(row.methods[0][1].unknown_reason == "method_observation_missing" for row in model.rows)
        assert model.rows[0].all_methods_state == "not_selected"
        assert model.rows[1].all_methods_state == "unknown"


@pytest.mark.parametrize("field,value,code", [
    ("artifact_sha256", None, "missing_evidence"),
    ("data_date", "2026-10-06", "data_date_mismatch"),
    ("artifact_sha256", "b" * 64, "stock_evidence_revision_or_date_mismatch"),
    ("unknown_reason", "missing", "unknown_qualification_mismatch"),
    ("reason", "", "reason_missing"),
])
def test_evidence_never_implies_selected_without_pins(tmp_path, field, value, code):
    sources, _ = _sources(tmp_path)
    changed = replace(sources[0].observations[0], **{field: value})
    _reject(code, lambda: build_multi_method_consensus((replace(sources[0], observations=(changed, sources[0].observations[1])), sources[1])))


def test_partial_snapshot_missing_stock_is_unknown_without_exit(tmp_path):
    pin, _ = _publish(tmp_path, {"2382": _snapshot_payload("2382")}, ("2382", "3034"))
    model = read_daily_market_consensus(DailyMarketSnapshotRepository(tmp_path), manifest_sha256=pin,
        cohort_id="ux19-test-cohort", decision_date=DECISION_DATE, as_of=PUBLISHED_AT)
    assert model.denominator == 2
    assert all(r.selected_method_count == 0 and r.all_methods_state == "unknown" for r in model.rows)
    assert "source_unavailable" in model.rows[1].methods[0][1].unknown_reason
    assert model.sources[0].observations[0].state == "selected"
    assert model.method_counts[0][1:] == (0, 0, 2)


def test_limits_and_non_sequence_rejected(tmp_path):
    sources, _ = _sources(tmp_path)
    for value in ((), sources * 5, iter(sources), "methods"):
        _reject("source_limit", lambda: build_multi_method_consensus(value))
    _reject("observation_limit", lambda: build_multi_method_consensus((replace(sources[0], observations=sources[0].observations * 17),)))


def test_adapter_after_asof_and_mutated_verified_payload_rejected(tmp_path):
    _, snapshot = _sources(tmp_path)
    _reject("source_after_as_of", lambda: adapt_daily_market_snapshot(snapshot, as_of=PUBLISHED_AT - timedelta(seconds=1)))
    altered = deepcopy(dict(snapshot.stock_snapshots))
    altered["2382"]["conditions"]["close_above_ma20"]["state"] = "no_match"
    _reject("artifact_mutated", lambda: adapt_daily_market_snapshot(replace(snapshot, stock_snapshots=altered), as_of=PUBLISHED_AT))
    manifest = deepcopy(dict(snapshot.manifest))
    manifest["cohort_id"] = "mutated"
    _reject("manifest_mutated", lambda: adapt_daily_market_snapshot(replace(snapshot, manifest=manifest), as_of=PUBLISHED_AT))


def test_repository_artifact_revision_and_latest_change(tmp_path):
    _, snapshot = _sources(tmp_path)
    # latest 改動不影響 pinned 讀取，也不允許悄悄選另一版本。
    (tmp_path / "latest.json").write_text("{}", encoding="utf-8")
    repo = DailyMarketSnapshotRepository(tmp_path)
    args = dict(manifest_sha256=snapshot.manifest_sha256, cohort_id=snapshot.cohort_id,
                decision_date=DECISION_DATE, as_of=PUBLISHED_AT)
    assert read_daily_market_consensus(repo, **args).denominator == 2
    record = snapshot.manifest["stocks"][0]
    (tmp_path / snapshot_artifact_relpath(record["artifact_sha256"])).write_text("{}", encoding="utf-8")
    with pytest.raises(DailyMarketSnapshotVerificationError):
        read_daily_market_consensus(repo, **args)


def test_repository_wrong_date_cohort_and_manifest_revision(tmp_path):
    _, snapshot = _sources(tmp_path)
    repo = DailyMarketSnapshotRepository(tmp_path)
    for day, cohort in ((DECISION_DATE + timedelta(days=1), snapshot.cohort_id), (DECISION_DATE, "other")):
        with pytest.raises(DailyMarketSnapshotVerificationError):
            read_daily_market_consensus(repo, manifest_sha256=snapshot.manifest_sha256, cohort_id=cohort,
                                        decision_date=day, as_of=PUBLISHED_AT)
    (tmp_path / snapshot_manifest_relpath(snapshot.manifest_sha256)).write_text("{}", encoding="utf-8")
    with pytest.raises(DailyMarketSnapshotVerificationError):
        read_daily_market_consensus(repo, manifest_sha256=snapshot.manifest_sha256, cohort_id=snapshot.cohort_id,
                                    decision_date=DECISION_DATE, as_of=PUBLISHED_AT)



def test_explicit_universe_excluded_reasons_and_population_preserved(tmp_path):
    from app_module.daily_market_research_universe import load_research_universe_spec
    universe_file = tmp_path / "cohort.json"
    universe_file.write_text(json.dumps({
        "schema_version": "daily-market-research-universe.v1", "universe_id": "ux19-test-cohort",
        "version": "1.0", "as_of_date": DECISION_DATE.isoformat(), "method": "daily-market-close-ma.v1",
        "included_stock_codes": ["2382", "3034"], "excluded_stock_codes": [{"stock_code": "1477", "reason": "不屬於固定研究母體。"}],
        "population_count": 3, "scope": "bounded_research_cohort", "research_only": True, "complete_fixed_cohort": True,
    }, ensure_ascii=False), encoding="utf-8")
    binding = load_research_universe_spec(universe_file).to_manifest_binding()
    pin, _ = _publish(tmp_path, {"2382": _snapshot_payload("2382"), "3034": _snapshot_payload("3034")},
                      ("2382", "3034"), manifest_updates={"research_universe": binding})
    model = read_daily_market_consensus(DailyMarketSnapshotRepository(tmp_path), manifest_sha256=pin,
        cohort_id="ux19-test-cohort", decision_date=DECISION_DATE, as_of=PUBLISHED_AT)
    assert model.denominator == 2 and model.population_count == 3
    assert model.excluded_stock_codes == (("1477", "不屬於固定研究母體。"),)
    assert all(json.loads(s.universe_json) == binding for s in model.sources)
    assert all(s.universe_sha256 == model.sources[0].universe_sha256 for s in model.sources)
    assert {r.stock_code for r in model.rows} == {"2382", "3034"}
    universe_file.write_text("{}", encoding="utf-8")
    with pytest.raises(DailyMarketSnapshotVerificationError):
        read_daily_market_consensus(DailyMarketSnapshotRepository(tmp_path), manifest_sha256=pin,
            cohort_id="ux19-test-cohort", decision_date=DECISION_DATE, as_of=PUBLISHED_AT)


def test_snapshot_method_contract_mixed_version_rejected_by_reader(tmp_path):
    from app_module.daily_market_method_contract import method_contracts_payload, method_contracts_sha256
    contracts = method_contracts_payload()
    contracts["close_above_ma60"]["version"] = "2.0.0"
    pin, _ = _publish(tmp_path, {"2382": _snapshot_payload("2382")}, ("2382",),
        manifest_updates={"method_contracts": contracts, "method_contracts_sha256": method_contracts_sha256(contracts)})
    with pytest.raises(DailyMarketSnapshotVerificationError):
        read_daily_market_consensus(DailyMarketSnapshotRepository(tmp_path), manifest_sha256=pin,
            cohort_id="ux19-test-cohort", decision_date=DECISION_DATE, as_of=PUBLISHED_AT)


def test_valid_different_decision_date_does_not_intersect(tmp_path):
    sources, _ = _sources(tmp_path)
    later = replace(sources[1], decision_date="2026-10-06", decision_cutoff="2026-10-06T16:00:00+08:00",
                    published_at="2026-10-06T12:00:00+00:00")
    _reject("incomparable_source_scope_or_revision", lambda: build_multi_method_consensus((sources[0], later)))


def test_per_stock_different_older_data_date_rejected(tmp_path):
    sources, _ = _sources(tmp_path)
    changed = replace(sources[1].observations[0], data_date="2026-10-03")
    _reject("stock_evidence_revision_or_date_mismatch", lambda: build_multi_method_consensus((sources[0], replace(sources[1], observations=(changed, sources[1].observations[1])))))


def test_unknown_never_counts_as_negative_when_no_other_negative(tmp_path):
    sources, _ = _sources(tmp_path)
    missing = replace(sources[1], observations=(sources[1].observations[1],))
    model = build_multi_method_consensus((sources[0], missing))
    assert model.rows[0].all_methods_state == "unknown"
    assert model.rows[0].methods[1][1].state == "unknown"
    assert model.method_counts[1][1:] == (0, 0, 2)


@pytest.mark.parametrize("change,code", [
    ({"excluded_stock_codes": (("2382", "outside"),)}, "exclusion_scope_invalid"),
    ({"excluded_stock_codes": (("1477", ""),)}, "exclusion_reason_missing"),
    ({"source_refs_json": "x" * 65537}, "source_refs_limit"),
    ({"universe_json": "x" * 32769}, "universe_byte_limit"),
    ({"decision_cutoff": "2026-10-05T16:00:00"}, "clock_identity_missing"),
    ({"decision_date": "not-a-date"}, "decision_date_invalid"),
])
def test_contract_resource_and_clock_bounds(tmp_path, change, code):
    sources, _ = _sources(tmp_path)
    _reject(code, lambda: build_multi_method_consensus((replace(sources[0], **change),)))


@pytest.mark.parametrize("refs,code", [("[]", "source_refs_missing"), ("{}", "source_refs_invalid"), ("bad", "source_refs_invalid")])
def test_missing_or_invalid_source_refs_never_qualify(tmp_path, refs, code):
    sources, _ = _sources(tmp_path)
    _reject(code, lambda: build_multi_method_consensus((replace(sources[0], source_refs_json=refs),)))



def test_state_relation_mismatch_never_counts(tmp_path):
    sources, _ = _sources(tmp_path)
    changed = replace(sources[0].observations[0], relation="below")
    _reject("state_relation_mismatch", lambda: build_multi_method_consensus((replace(sources[0], observations=(changed, sources[0].observations[1])),)))
