"""A01 有限上軌比較、舊版身份與隔離保存鏈的工程驗證。"""

from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app_module.daily_market_cohort_projection import project_daily_market_cohort
from app_module.daily_market_feature_snapshot import (
    DAILY_MARKET_FEATURE_CONTRACT_VERSION,
    DAILY_MARKET_FEATURE_CONTRACT_VERSION_BBANDS30_UPPER,
    DailyMarketFeatureSnapshotService,
    feature_contract_for_version,
)
from app_module.daily_market_method_contract import method_contracts_payload, method_contracts_sha256
from app_module.daily_market_research_capabilities import project_daily_market_research_capabilities
from app_module.daily_market_research_screener import (
    DailyMarketResearchScreenerService, evaluate_daily_market_conditions,
)
from app_module.daily_market_snapshot_producer import DailyMarketSnapshotProducer
from app_module.daily_market_snapshot_repository import (
    DailyMarketSnapshotRepository,
    DailyMarketSnapshotVerificationError,
)
from app_module.daily_market_snapshot_source import SQLiteDailyMarketSnapshotSource
from app_module.stock_research_report_dtos import StockMetricDTO
from tests.test_daily_market_feature_snapshot import _prices, _technical
from tests.test_daily_market_snapshot_consumer import _seed
from tests.test_daily_market_snapshot_producer import _capacity_probe


V3 = DAILY_MARKET_FEATURE_CONTRACT_VERSION_BBANDS30_UPPER
METHOD = "close_above_bbands30_upper"
COHORT = "synthetic-offline-a01"


def _band(value=Decimal("150"), *, count=60):
    points = _prices(count)
    technical = _technical(points[-1].data_date)
    metric = StockMetricDTO(
        key="BB_Upper", label="BB_Upper", value=value, unit="TWD/share",
        data_as_of=points[-1].data_date, source_id="sqlite.technical_indicators",
        quality="observed",
    )
    return points, replace(technical, indicators=(*technical.indicators, metric))


def _project(points, technical, *, decision_date=None, version=V3):
    return DailyMarketFeatureSnapshotService().project(
        "2382", decision_date or date.fromisoformat(points[-1].data_date),
        "stock-report-symbol:2382", points, technical, contract_version=version,
    )


def test_v2_all_pins_remain_exact_and_v3_registry_is_detached():
    points = _prices(60)
    result = _project(points, _technical(points[-1].data_date), version=DAILY_MARKET_FEATURE_CONTRACT_VERSION)
    assert method_contracts_sha256() == "029bcb5ada592619d9748d327eef509db0642a1c6904b652b31f186027025dc5"
    assert result.input_fingerprint_sha256 == "485832355546a911852cd74f70b07f90adb668f36663f9123e22ad5239017c67"
    assert result.snapshot_identity_sha256 == "82b91a12471e7fa3ec39cf633311b6b79dcf30f11fe55da6def91aa0656003bf"
    raw = json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(raw).hexdigest() == "819e6f0c95f0f8418787b7210f55f6d9da3efe7bd4d1c05f05b6e1fd911bead6"
    v2, v3 = feature_contract_for_version(DAILY_MARKET_FEATURE_CONTRACT_VERSION), feature_contract_for_version(V3)
    assert v2.feature_keys == ("close", "MA20", "MA60")
    assert v3.feature_keys == (*v2.feature_keys, "BB_Upper")
    assert {key: v3.method_contracts[key] for key in v2.condition_keys} == v2.method_contracts
    contract = v3.method_contracts[METHOD]
    assert contract["parameters"] == {
        "timeperiod": 30, "nbdevup": "2.0", "nbdevdn": "2.0", "matype": "SMA", "direction": "above",
    }
    contract["parameters"]["timeperiod"] = 99
    assert v3.method_contracts[METHOD]["parameters"]["timeperiod"] == 30
    assert METHOD not in method_contracts_payload()


@pytest.mark.parametrize("upper,state,relation", [
    (Decimal("158.999999999999999999"), "match", "above"),
    (Decimal("159"), "no_match", "equal"),
    (Decimal("159.000000000000000001"), "no_match", "below"),
])
def test_strict_decimal_comparison_preserves_precision(upper, state, relation):
    points, technical = _band(upper)
    result = _project(points, technical)
    assert result.condition(METHOD).state == state
    assert result.condition(METHOD).relation == relation
    assert result.feature("BB_Upper").value == upper
    assert result.feature("BB_Upper").warmup_required_count == 30
    assert result.official_availability_state == "unknown"
    assert result.market_calendar_completeness == "unknown"
    assert result.historical_pit_eligible is False


@pytest.mark.parametrize("value", [None, Decimal("NaN"), Decimal("Infinity"), Decimal("0"), Decimal("-1"), 150])
def test_missing_nonfinite_and_non_decimal_band_remain_unknown(value):
    points, technical = _band(value)
    result = _project(points, technical)
    assert result.feature("BB_Upper").state == "unknown"
    assert result.feature("BB_Upper").value is None
    assert result.condition(METHOD).state == "unknown"
    assert result.condition(METHOD).eligibility == "unknown"


@pytest.mark.parametrize("mutation,reason", [
    ("warmup", "insufficient_valid_ohlc_streak"),
    ("gap", "invalid_ohlc_row"),
    ("missing", "technical_metric_missing"),
    ("duplicate", "duplicate_technical_metric"),
    ("metric_date", "technical_metric_date_mismatch"),
    ("quality", "technical_metric_not_observed"),
    ("source", "technical_source_identity_missing"),
    ("future", "future_market_date"),
])
def test_warmup_source_quality_and_time_guards(mutation, reason):
    points, technical = _band(count=29 if mutation == "warmup" else 60)
    metric = technical.indicators[-1]
    decision = date.fromisoformat(points[-1].data_date)
    if mutation == "gap":
        points = (*points[:-2], replace(points[-2], close_price=None), points[-1])
    elif mutation == "missing":
        technical = replace(technical, indicators=technical.indicators[:-1])
    elif mutation == "duplicate":
        technical = replace(technical, indicators=(*technical.indicators, metric))
    elif mutation == "metric_date":
        metric = replace(metric, data_as_of=(decision - timedelta(days=1)).isoformat())
        technical = replace(technical, indicators=(*technical.indicators[:-1], metric))
    elif mutation == "quality":
        metric = replace(metric, quality="unknown")
        technical = replace(technical, indicators=(*technical.indicators[:-1], metric))
    elif mutation == "source":
        metric = replace(metric, source_id="")
        technical = replace(technical, source_id="", indicators=(*technical.indicators[:-1], metric))
    elif mutation == "future":
        decision -= timedelta(days=1)
    result = _project(points, technical, decision_date=decision)
    assert result.feature("BB_Upper").state == "unknown"
    assert result.condition(METHOD).state == "unknown"
    assert result.condition(METHOD).unknown_reason == reason


def _database(tmp_path, *, with_band=True):
    db, day = _seed(tmp_path)
    if with_band:
        with sqlite3.connect(db) as connection:
            connection.execute("ALTER TABLE technical_indicators ADD COLUMN BB_Upper TEXT")
            connection.execute("UPDATE technical_indicators SET BB_Upper='100.5'")
    return db, day


def _publish(db, day, root, *, version=V3):
    cutoff = datetime.combine(day, time(16), tzinfo=ZoneInfo("Asia/Taipei"))
    with SQLiteDailyMarketSnapshotSource(db, day) as source:
        def load(code, requested):
            assert requested == day
            return source.load_input(code, include_bbands30_upper=version == V3)
        return DailyMarketSnapshotProducer(
            root, capacity_probe=_capacity_probe(), clock=lambda: cutoff + timedelta(hours=1),
        ).produce(
            cohort_id=COHORT, decision_cutoff=cutoff, stock_codes=("2382",),
            source_loader=load, before_publish=source.validate_source_stable, contract_version=version,
        )


def test_real_isolated_source_publish_screener_capability_and_new_process_readback(tmp_path):
    db, day = _database(tmp_path)
    root = tmp_path / "snapshots"
    before = hashlib.sha256(db.read_bytes()).hexdigest(), db.stat().st_mtime_ns
    with SQLiteDailyMarketSnapshotSource(db, day) as source:
        legacy = source.load_input("2382")
        assert all(item.key != "BB_Upper" for item in legacy.technical.indicators)
    result = _publish(db, day, root)
    assert result.status == "published_complete", result.to_dict()
    assert (hashlib.sha256(db.read_bytes()).hexdigest(), db.stat().st_mtime_ns) == before
    repository = DailyMarketSnapshotRepository(root)
    saved = repository.load_manifest(result.manifest_sha256, cohort_id=COHORT, decision_date=day)
    payload = saved.stock_snapshots["2382"]
    assert payload["features"]["BB_Upper"]["value"] == "100.5"
    assert payload["conditions"][METHOD]["state"] == "match"
    service = DailyMarketResearchScreenerService(SimpleNamespace(db_file=db), root)
    verified = service.read_snapshot(COHORT, day, result.manifest_sha256)
    rows = service.filter_rows(verified, feature_contract_for_version(V3).condition_keys, "AND")
    projection = project_daily_market_cohort(verified, rows, expected_snapshot_root=root)
    assert projection.members[0].condition(METHOD).state == "match"
    report = project_daily_market_research_capabilities(verified, rows, expected_snapshot_root=root)
    assert METHOD in [item.key for item in report.catalog.methods]
    assert json.loads(report.catalog.features[-1].warmup_json)["parameter_lineage_verified"] is False
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE technical_indicators SET BB_Upper='999'")
    with pytest.raises(DailyMarketSnapshotVerificationError) as revision_error:
        service.read_snapshot(COHORT, day, result.manifest_sha256)
    assert revision_error.value.code == "snapshot_input_hash_mismatch"
    script = """import json,sys
from datetime import date
from app_module.daily_market_snapshot_repository import DailyMarketSnapshotRepository
s=DailyMarketSnapshotRepository(sys.argv[1]).load_manifest(sys.argv[2],cohort_id=sys.argv[3],decision_date=date.fromisoformat(sys.argv[4]))
p=s.stock_snapshots['2382']
print(json.dumps({'manifest':s.manifest_sha256,'identity':p['snapshot_identity_sha256'],'input':p['input_fingerprint_sha256'],'upper':p['features']['BB_Upper']['value'],'pit':p['policy']['historical_pit_eligible']}))
"""
    child = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", script, str(root), result.manifest_sha256, COHORT, day.isoformat()],
        capture_output=True, text=True, encoding="utf-8", timeout=30, cwd=Path(__file__).resolve().parents[1],
    )
    assert child.returncode == 0, child.stderr
    assert json.loads(child.stdout) == {
        "manifest": saved.manifest_sha256, "identity": payload["snapshot_identity_sha256"],
        "input": payload["input_fingerprint_sha256"], "upper": "100.5", "pit": False,
    }


def test_version_switch_preserves_old_artifacts_and_missing_band_is_saved_unknown(tmp_path):
    db, day = _database(tmp_path, with_band=False)
    root = tmp_path / "snapshots"
    v2 = _publish(db, day, root, version=DAILY_MARKET_FEATURE_CONTRACT_VERSION)
    assert v2.status == "published_complete", v2.to_dict()
    original_files = {p: p.read_bytes() for p in root.rglob("*.json") if p.name != "latest.json"}
    v3 = _publish(db, day, root)
    assert v3.status == "published_complete", v3.to_dict()
    assert v3.reused_stock_codes == ()
    assert v3.recomputed_stock_codes == ("2382",)
    assert all(p.read_bytes() == value for p, value in original_files.items())
    repository = DailyMarketSnapshotRepository(root)
    old = repository.load_manifest(v2.manifest_sha256, cohort_id=COHORT, decision_date=day)
    new = repository.load_manifest(v3.manifest_sha256, cohort_id=COHORT, decision_date=day)
    assert METHOD not in old.stock_snapshots["2382"]["conditions"]
    assert new.stock_snapshots["2382"]["conditions"][METHOD]["state"] == "unknown"
    assert new.stock_snapshots["2382"]["conditions"][METHOD]["unknown_reason"] == "technical_metric_missing"


@pytest.mark.parametrize("version,mutation", [
    (DAILY_MARKET_FEATURE_CONTRACT_VERSION, "extra"), (V3, "missing"),
])
def test_repository_rejects_cross_version_feature_schema(tmp_path, version, mutation):
    db, day = _database(tmp_path)
    root = tmp_path / "snapshots"
    result = _publish(db, day, root, version=version)
    assert result.status == "published_complete", result.to_dict()
    repository = DailyMarketSnapshotRepository(root)
    saved = repository.load_manifest(result.manifest_sha256, cohort_id=COHORT, decision_date=day)
    payload = deepcopy(saved.stock_snapshots["2382"])
    if mutation == "extra":
        payload["features"]["BB_Upper"] = deepcopy(payload["features"]["MA20"])
    else:
        payload["features"].pop("BB_Upper")
    with pytest.raises(DailyMarketSnapshotVerificationError) as error:
        repository._validate_snapshot_payload(
            payload, record=dict(saved.manifest["stocks"][0]), stock_code="2382",
            decision_date=day, manifest=dict(saved.manifest),
        )
    assert error.value.code == "snapshot_feature_schema_mismatch"


def test_unknown_version_and_non_bool_optin_are_rejected():
    with pytest.raises(ValueError):
        feature_contract_for_version("daily-market-feature-snapshot.unapproved")
    with pytest.raises(TypeError):
        method_contracts_payload(include_bbands30_upper="False")


def test_new_band_method_requires_binding_and_rejects_wrong_parameters():
    unbound = evaluate_daily_market_conditions(
        {METHOD: {"state": "match", "relation": "above"}}, (METHOD,), "AND",
    ).conditions[0]
    assert unbound.state == "unknown"
    assert unbound.eligibility == "unknown"
    assert unbound.unknown_reason == "method_contract_invalid"
    points, technical = _band()
    payload = _project(points, technical).to_dict()["conditions"][METHOD]
    payload["parameters"]["timeperiod"] = 20
    mismatched = evaluate_daily_market_conditions(
        {METHOD: payload}, (METHOD,), "AND",
        expected_decision_date=date.fromisoformat(points[-1].data_date),
    ).conditions[0]
    assert mismatched.state == "unknown"
    assert mismatched.eligibility == "unknown"


@pytest.mark.parametrize("version", [DAILY_MARKET_FEATURE_CONTRACT_VERSION, V3])
def test_central_report_consumer_uses_saved_feature_version(tmp_path, version):
    from tests.test_daily_market_snapshot_consumer import _consumer

    db, day = _database(tmp_path)
    root = tmp_path / "snapshots"
    published = _publish(db, day, root, version=version)
    assert published.status == "published_complete"
    report = _consumer(db, day, root, cohort=COHORT).read_report("2382", as_of_date=day)
    assert report.shared_daily_features["readback"]["mode"] == "verified_published_research_snapshot"
    assert report.shared_daily_features["contract_version"] == version
    assert ("BB_Upper" in report.shared_daily_features["features"]) is (version == V3)
    if version == V3:
        assert report.shared_daily_features["conditions"][METHOD]["state"] == "match"
        with sqlite3.connect(db) as connection:
            connection.execute("UPDATE technical_indicators SET BB_Upper='999'")
        changed = _consumer(db, day, root, cohort=COHORT).read_report("2382", as_of_date=day)
        assert changed.shared_daily_features["projection_status"] == "failed"


@pytest.mark.parametrize("version,method_count", [(DAILY_MARKET_FEATURE_CONTRACT_VERSION, 2), (V3, 3)])
def test_central_versioned_capture_preserves_all_method_denominators(tmp_path, monkeypatch, version, method_count):
    from app_module.rule_research_sample_capture import build_rule_research_capture, RuleResearchCapture
    from tests.test_rule_research_sample_capture import _writer

    db, day = _database(tmp_path)
    root = tmp_path / "snapshots"
    published = _publish(db, day, root, version=version)
    saved = DailyMarketSnapshotRepository(root).load_manifest(
        published.manifest_sha256, cohort_id=COHORT, decision_date=day,
    )
    clock = datetime.fromisoformat(saved.manifest["published_at"])
    capture = build_rule_research_capture(saved, as_of=clock, observed_at=clock)
    body = capture.to_dict()
    assert len(body["method_counts"]) == len(body["rows"]) == method_count
    assert all(item["included_denominator"] == 1 for item in body["method_counts"])
    assert all(item["represented_denominator"] == 1 for item in body["method_counts"])
    assert body["feature_contract_version"] == version
    assert body["policy"]["formal_eligible"] is False
    written = _writer(tmp_path, monkeypatch).write(capture, revalidate=lambda: capture)
    stored = Path(written["directory"]) / "capture.json"
    assert RuleResearchCapture(stored.read_text(encoding="utf-8")).identity_sha256 == capture.identity_sha256
    if version == V3:
        import app_module.rule_research_sample_capture as capture_module

        forged = deepcopy(body)
        forged["rows"][-1]["stock_code"] = "3333"
        forged["capture_identity_sha256"] = capture_module._identity(forged)
        with pytest.raises(capture_module.RuleSampleCaptureError) as error:
            RuleResearchCapture(capture_module._json(forged)).to_dict()
        assert error.value.code == "capture_method_scope_mismatch"


@pytest.mark.parametrize("version", [DAILY_MARKET_FEATURE_CONTRACT_VERSION, V3])
def test_central_pinned_report_keeps_exact_saved_version(tmp_path, version):
    from tests.test_daily_market_snapshot_consumer import _consumer

    db, day = _database(tmp_path)
    root = tmp_path / "snapshots"
    published = _publish(db, day, root, version=version)
    saved = DailyMarketSnapshotRepository(root).load_manifest(
        published.manifest_sha256, cohort_id=COHORT, decision_date=day,
    )
    context = {"source_kind": "daily_market_research_snapshot", "decision_date": day.isoformat(),
               "daily_snapshot_root": str(root), "daily_snapshot_cohort_id": COHORT,
               "source_snapshot_hash": saved.manifest_sha256,
               "source_snapshot_id": saved.manifest_identity_sha256,
               "daily_snapshot_condition_keys": METHOD if version == V3 else "close_above_ma20",
               "daily_snapshot_combine_mode": "AND"}
    report = _consumer(db, day, root, cohort=COHORT).read_report("2382", as_of_date=day, context=context)
    assert report.shared_daily_features["readback"]["mode"] == "verified_pinned_daily_market_research_snapshot"
    assert report.shared_daily_features["contract_version"] == version
    assert report.shared_daily_features["readback"]["manifest_sha256"] == saved.manifest_sha256
