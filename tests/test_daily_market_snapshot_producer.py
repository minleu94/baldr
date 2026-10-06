from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import pytest

from app_module.daily_market_feature_snapshot import DailyMarketFeatureSnapshotService
from app_module import daily_market_method_contract
from app_module.daily_market_snapshot_producer import (
    DailyMarketSnapshotInput,
    DailyMarketSnapshotProducer,
)
from app_module.daily_market_snapshot_repository import (
    DAILY_MARKET_SNAPSHOT_LEGACY_MANIFEST_SCHEMA,
    DAILY_MARKET_SNAPSHOT_MAX_ARTIFACT_BYTES,
    DAILY_MARKET_SNAPSHOT_POINTER_SCHEMA,
    DailyMarketSnapshotRepository,
    DailyMarketSnapshotVerificationError,
    canonical_json_bytes,
    snapshot_artifact_relpath,
    snapshot_identity_sha256,
    snapshot_manifest_identity_sha256,
    snapshot_manifest_relpath,
)
from app_module.stock_research_report_dtos import (
    StockMetricDTO,
    StockPricePointDTO,
    StockTechnicalSnapshotDTO,
)
from data_module.ml_storage_capacity import CANONICAL_HEAVY_CHAIN_SAFETY_RESERVE_BYTES


DECISION_DATE = date(2026, 10, 5)
TAIPEI = ZoneInfo("Asia/Taipei")
CUTOFF = datetime(2026, 10, 5, 15, 0, tzinfo=TAIPEI)
CLOCK_NOW = datetime(2026, 10, 5, 16, 0, tzinfo=TAIPEI)
SCHEMA_SHA = "a" * 64
DATABASE = r"C:\fixture\market.sqlite"


def _capacity_probe(free_bytes: int | None = None):
    free = (
        CANONICAL_HEAVY_CHAIN_SAFETY_RESERVE_BYTES + 2**30
        if free_bytes is None
        else free_bytes
    )
    total = free + 100 * 2**30

    def probe(path: Path) -> Mapping[str, Any]:
        return {
            "probe_path": str(path),
            "total_bytes": total,
            "used_bytes": total - free,
            "free_bytes": free,
        }

    return probe


@pytest.mark.skipif(__import__("os").name != "nt", reason="Windows UTF16長路徑回歸")
def test_b12_deep_unicode_producer_repository_new_process_preserves_source(tmp_path):
    import os
    import subprocess
    import sys
    from app_module.daily_market_snapshot_source import SQLiteDailyMarketSnapshotSource
    from app_module.personal_data_paths import to_internal_io_path
    from tests.test_daily_market_snapshot_consumer import _seed
    db, day = _seed(tmp_path)
    before = (hashlib.sha256(db.read_bytes()).hexdigest(), db.stat().st_mtime_ns)
    root = tmp_path / ("深層研究😀"*12) / ("唯讀快照來源"*12) / "explicit-segment-for-deep-io" / "snapshot"
    assert len(str(root).encode("utf-16-le"))//2 > 260
    cutoff = datetime.combine(day, datetime.min.time(), tzinfo=TAIPEI)
    with SQLiteDailyMarketSnapshotSource(db, day) as source:
        result = DailyMarketSnapshotProducer(root, capacity_probe=_capacity_probe()).produce(
            cohort_id="synthetic-offline-deep", decision_cutoff=cutoff, stock_codes=("2382",),
            source_loader=lambda code, requested: source.load_input(code), before_publish=source.validate_source_stable)
    assert result.status == "published_complete", result.error_message
    read = DailyMarketSnapshotRepository(root).load_manifest(result.manifest_sha256,
        cohort_id="synthetic-offline-deep", decision_date=day)
    identity = read.manifest["manifest_identity_sha256"]
    assert not str(root).startswith("\\\\?\\")
    raw_pins = {str(p): hashlib.sha256(open(to_internal_io_path(p), "rb").read()).hexdigest()
                for p in [root/"latest.json", root/snapshot_manifest_relpath(result.manifest_sha256)]}
    script = "import json,sys;from datetime import date;from app_module.daily_market_snapshot_repository import DailyMarketSnapshotRepository; r=DailyMarketSnapshotRepository(sys.argv[1]).load_manifest(sys.argv[2],cohort_id='synthetic-offline-deep',decision_date=date.fromisoformat(sys.argv[3])); print(json.dumps({'sha':r.manifest_sha256,'identity':r.manifest['manifest_identity_sha256'],'source':r.manifest['stocks'][0]['source_refs']['database']}))"
    child = subprocess.run([sys.executable, "-X", "utf8", "-c", script, str(root), result.manifest_sha256, day.isoformat()],
        capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert child.returncode == 0, child.stderr
    saved = json.loads(child.stdout)
    assert saved["sha"] == result.manifest_sha256 and saved["identity"] == identity
    assert saved["source"] == str(db.resolve()) and "\\\\?\\" not in child.stdout
    assert before == (hashlib.sha256(db.read_bytes()).hexdigest(), db.stat().st_mtime_ns)
    assert raw_pins == {p: hashlib.sha256(open(to_internal_io_path(p), "rb").read()).hexdigest() for p in raw_pins}


@pytest.mark.skipif(__import__("os").name != "nt", reason="Windows實體alias回歸")
@pytest.mark.parametrize("suffix", ["alias.", "alias ", "alias:stream", "NUL"])
def test_b12_producer_rejects_windows_physical_alias_before_write(tmp_path, suffix):
    actual = tmp_path/"alias"
    actual.mkdir()
    sentinel = actual/"source-sentinel.json"
    sentinel.write_bytes(b'{"synthetic_offline":true}')
    with pytest.raises(ValueError, match="ambiguous_windows_path"):
        DailyMarketSnapshotProducer(tmp_path/suffix, capacity_probe=_capacity_probe())
    assert sentinel.read_bytes() == b'{"synthetic_offline":true}'


def _price_points(stock_code: str, *, offset: int = 0) -> tuple[StockPricePointDTO, ...]:
    dates: list[date] = []
    cursor = DECISION_DATE
    while len(dates) < 60:
        if cursor.weekday() < 5:
            dates.append(cursor)
        cursor -= timedelta(days=1)
    dates.reverse()
    rows = []
    for index, market_date in enumerate(dates):
        close = Decimal(100 + index + offset)
        rows.append(
            StockPricePointDTO(
                data_date=market_date.isoformat(),
                open_price=close,
                high_price=close + Decimal("2"),
                low_price=close - Decimal("2"),
                close_price=close,
                volume=1000 + index,
                turnover=close * Decimal(1000 + index),
                change=Decimal("0"),
                available_at="2026-10-05T14:00:00+08:00",
                source_id="sqlite.daily_prices",
                source_snapshot_hash=f"{stock_code}-price-{index:03d}",
                quality="observed",
            )
        )
    return tuple(rows)


def _input(stock_code: str, *, offset: int = 0) -> DailyMarketSnapshotInput:
    points = _price_points(stock_code, offset=offset)
    market_date = points[-1].data_date
    technical = StockTechnicalSnapshotDTO(
        data_date=market_date,
        indicators=(
            StockMetricDTO(
                key="MA20",
                label="MA20",
                value=Decimal("150.25"),
                unit="TWD/share",
                data_as_of=market_date,
                source_id="sqlite.technical_indicators",
                quality="observed",
            ),
            StockMetricDTO(
                key="MA60",
                label="MA60",
                value=Decimal("140.75"),
                unit="TWD/share",
                data_as_of=market_date,
                source_id="sqlite.technical_indicators",
                quality="observed",
            ),
        ),
        available_at="2026-10-05T14:00:00+08:00",
        source_id="sqlite.technical_indicators",
        quality="observed",
    )
    return DailyMarketSnapshotInput(
        stock_code=stock_code,
        scope_identity=f"sqlite:{SCHEMA_SHA}:stock:{stock_code}",
        price_points=points,
        technical=technical,
        source_refs={
            "database": DATABASE,
            "schema_identity_sha256": SCHEMA_SHA,
            "price": f"{DATABASE}#daily_prices",
            "technical": f"{DATABASE}#technical_indicators",
        },
    )


def _loader(inputs: Mapping[str, DailyMarketSnapshotInput], calls: list[str] | None = None):
    def load(stock_code: str, requested_date: date) -> DailyMarketSnapshotInput:
        assert requested_date == DECISION_DATE
        if calls is not None:
            calls.append(stock_code)
        return inputs[stock_code]

    return load


def _producer(root: Path, *, feature_service=None, capacity_probe=None):
    return DailyMarketSnapshotProducer(
        root,
        clock=lambda: CLOCK_NOW,
        feature_service=feature_service,
        capacity_probe=capacity_probe or _capacity_probe(),
    )


def _produce(producer: DailyMarketSnapshotProducer, inputs, **kwargs):
    return producer.produce(
        cohort_id="ux19-test-cohort",
        decision_cutoff=CUTOFF,
        stock_codes=tuple(inputs),
        source_loader=_loader(inputs),
        **kwargs,
    )


def _repin_as_legacy_v1(root: Path) -> tuple[bytes, str, bytes]:
    """將 fixture 的 latest 轉為舊 reader 可辨識的 v1 immutable 形狀。"""

    pointer_path = root / "latest.json"
    pointer = json.loads(pointer_path.read_bytes())
    manifest_path = root / Path(snapshot_manifest_relpath(pointer["manifest_sha256"]))
    manifest = json.loads(manifest_path.read_bytes())
    legacy_feature_version = "daily-market-feature-snapshot.v1"

    for record in manifest["stocks"]:
        artifact_path = root / Path(record["artifact_relpath"])
        payload = json.loads(artifact_path.read_bytes())
        payload["contract_version"] = legacy_feature_version
        payload.pop("method_contracts", None)
        payload.pop("method_contracts_sha256", None)
        for condition in payload["conditions"].values():
            for field in (
                "method_id",
                "family",
                "version",
                "parameters",
                "decision_date",
                "eligibility",
                "unknown_reason",
            ):
                condition.pop(field, None)
        payload["snapshot_identity_sha256"] = snapshot_identity_sha256(
            contract_version=legacy_feature_version,
            stock_code=payload["stock_code"],
            decision_date=payload["decision_date"],
            scope_identity=payload["scope_identity"],
            input_fingerprint_sha256=payload["input_fingerprint_sha256"],
        )
        artifact_bytes = canonical_json_bytes(payload)
        artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
        artifact_relpath = snapshot_artifact_relpath(artifact_sha256)
        (root / Path(artifact_relpath)).write_bytes(artifact_bytes)
        record["artifact_sha256"] = artifact_sha256
        record["artifact_relpath"] = artifact_relpath
        record["snapshot_identity_sha256"] = payload["snapshot_identity_sha256"]

    manifest["schema_version"] = DAILY_MARKET_SNAPSHOT_LEGACY_MANIFEST_SCHEMA
    manifest["feature_contract_version"] = legacy_feature_version
    manifest.pop("method_contracts", None)
    manifest.pop("method_contracts_sha256", None)
    manifest["method_versions"] = {
        "close": "existing_observation",
        "MA20": "existing_observation",
        "MA60": "existing_observation",
        "conditions": "existing_observation",
    }
    manifest["manifest_identity_sha256"] = snapshot_manifest_identity_sha256(manifest)
    manifest_bytes = canonical_json_bytes(manifest)
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    (root / Path(snapshot_manifest_relpath(manifest_sha256))).write_bytes(manifest_bytes)
    pointer_bytes = canonical_json_bytes(
        {
            "schema_version": DAILY_MARKET_SNAPSHOT_POINTER_SCHEMA,
            "manifest_sha256": manifest_sha256,
        }
    )
    pointer_path.write_bytes(pointer_bytes)
    return pointer_bytes, manifest_sha256, manifest_bytes


def test_first_publish_reader_roundtrip_and_exact_noop_preserves_latest(tmp_path: Path):
    inputs = {code: _input(code) for code in ("1101", "2382")}
    producer = _producer(tmp_path / "snapshot")

    first = _produce(producer, inputs)

    assert first.status == "published_complete"
    assert first.published is True
    assert first.recomputed_stock_codes == ("1101", "2382")
    assert first.reused_stock_codes == ()
    assert first.capacity_preflight["safety_reserve_bytes"] == CANONICAL_HEAVY_CHAIN_SAFETY_RESERVE_BYTES
    assert 0 < first.persistent_new_bytes <= 8 * 1024 * 1024
    assert first.temporary_peak_bytes <= 8 * 1024 * 1024

    repository = DailyMarketSnapshotRepository(producer.root)
    verified = repository.load_latest(
        cohort_id="ux19-test-cohort",
        decision_date=DECISION_DATE,
        expected_stock_codes=("1101", "2382"),
    )
    assert set(verified.stock_snapshots) == {"1101", "2382"}
    assert verified.manifest["missing_stocks"] == []
    assert verified.manifest["completeness"] == "complete_declared_cohort"
    assert verified.manifest["policy"] == {
        "research_only": True,
        "historical_pit_eligible": False,
    }
    assert all(
        (producer.root / record["artifact_relpath"]).stat().st_size
        <= DAILY_MARKET_SNAPSHOT_MAX_ARTIFACT_BYTES
        for record in verified.manifest["stocks"]
    )

    pointer_before = (producer.root / "latest.json").read_bytes()
    manifest_before = verified.manifest["published_at"]
    second = _produce(producer, inputs)
    verified_again = repository.load_latest(
        cohort_id="ux19-test-cohort", decision_date=DECISION_DATE
    )
    assert second.status == "unchanged"
    assert second.published is False
    assert second.reused_stock_codes == ("1101", "2382")
    assert (producer.root / "latest.json").read_bytes() == pointer_before
    assert verified_again.manifest["published_at"] == manifest_before


def test_legacy_v1_requires_explicit_production_and_keeps_old_immutables(tmp_path: Path):
    root = tmp_path / "legacy-v1"
    producer = _producer(root)
    original = {"2382": _input("2382")}
    assert _produce(producer, original).status == "published_complete"
    legacy_pointer, legacy_manifest_sha256, legacy_manifest_bytes = _repin_as_legacy_v1(root)
    legacy_manifest_path = root / Path(snapshot_manifest_relpath(legacy_manifest_sha256))

    with pytest.raises(DailyMarketSnapshotVerificationError) as error:
        DailyMarketSnapshotRepository(root).load_latest(
            cohort_id="ux19-test-cohort", decision_date=DECISION_DATE
        )
    assert error.value.code == "snapshot_manifest_legacy_v1"
    assert "v2" in str(error.value)

    immutable_before_failure = {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*.json")
        if path.name != "latest.json"
    }
    source_calls: list[str] = []

    def unavailable(stock_code: str, requested_date: date):
        source_calls.append(stock_code)
        raise RuntimeError("fixture source unavailable")

    failed = producer.produce(
        cohort_id="ux19-test-cohort",
        decision_cutoff=CUTOFF,
        stock_codes=("2382",),
        source_loader=unavailable,
    )
    assert failed.status == "source_unavailable"
    assert failed.published is False
    assert failed.rebuild_reason == "legacy_v1_requires_explicit_reproduction"
    assert source_calls == ["2382"]
    assert (root / "latest.json").read_bytes() == legacy_pointer
    assert legacy_manifest_path.read_bytes() == legacy_manifest_bytes
    assert {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*.json")
        if path.name != "latest.json"
    } == immutable_before_failure

    revised = {"2382": _input("2382", offset=1)}
    reproduced = _produce(producer, revised)
    assert reproduced.status == "published_complete"
    assert reproduced.published is True
    assert reproduced.rebuild_reason == "legacy_v1_requires_explicit_reproduction"
    assert reproduced.reused_stock_codes == ()
    assert reproduced.recomputed_stock_codes == ("2382",)
    verified = DailyMarketSnapshotRepository(root).load_latest(
        cohort_id="ux19-test-cohort", decision_date=DECISION_DATE
    )
    assert verified.manifest["schema_version"] == "daily-market-snapshot-manifest.v2"
    assert verified.manifest_sha256 == reproduced.manifest_sha256
    assert legacy_manifest_path.read_bytes() == legacy_manifest_bytes
    for relative_path, immutable_bytes in immutable_before_failure.items():
        assert (root / relative_path).read_bytes() == immutable_bytes


@pytest.mark.parametrize(
    ("mutation", "expected_error_code"),
    [
        ("version", "snapshot_method_contract_mismatch"),
        ("parameters", "snapshot_method_contract_registry_invalid"),
    ],
)
def test_changed_method_registry_never_reuses_existing_v2_producer_snapshot(
    tmp_path: Path, monkeypatch, mutation: str, expected_error_code: str
):
    root = tmp_path / mutation
    inputs = {"2382": _input("2382")}
    producer = _producer(root)
    assert _produce(producer, inputs).status == "published_complete"
    pointer_before = (root / "latest.json").read_bytes()
    immutable_before = {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*.json")
        if path.name != "latest.json"
    }

    changed_contract = deepcopy(daily_market_method_contract._METHOD_CONTRACTS["close_above_ma20"])
    if mutation == "version":
        changed_contract["version"] = "1.0.1"
    else:
        changed_contract["parameters"]["window"] = 21
    monkeypatch.setitem(
        daily_market_method_contract._METHOD_CONTRACTS,
        "close_above_ma20",
        changed_contract,
    )

    calls: list[str] = []

    def track_source(stock_code: str, requested_date: date):
        calls.append(stock_code)
        return inputs[stock_code]

    blocked = producer.produce(
        cohort_id="ux19-test-cohort",
        decision_cutoff=CUTOFF,
        stock_codes=("2382",),
        source_loader=track_source,
    )
    assert blocked.status == "prior_snapshot_invalid"
    assert blocked.published is False
    assert blocked.reused_stock_codes == ()
    assert blocked.error_code == expected_error_code
    assert calls == []
    assert (root / "latest.json").read_bytes() == pointer_before
    assert {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*.json")
        if path.name != "latest.json"
    } == immutable_before

    fresh_root_producer = _producer(tmp_path / f"fresh-{mutation}")
    if mutation == "version":
        fresh = _produce(fresh_root_producer, inputs)
        assert fresh.status == "published_complete"
        refreshed = DailyMarketSnapshotRepository(fresh_root_producer.root).load_latest(
            cohort_id="ux19-test-cohort", decision_date=DECISION_DATE
        )
        assert refreshed.stock_snapshots["2382"]["conditions"]["close_above_ma20"]["version"] == "1.0.1"
    else:
        fresh = _produce(fresh_root_producer, inputs)
        assert fresh.status == "prior_snapshot_invalid"
        assert fresh.error_code == "snapshot_method_contract_registry_invalid"
        assert fresh.reused_stock_codes == ()


def test_incremental_source_revision_matches_fresh_full_projection(tmp_path: Path, monkeypatch):
    initial_inputs = {code: _input(code) for code in ("1101", "2382")}
    incremental_root = tmp_path / "incremental"
    service = DailyMarketFeatureSnapshotService()
    original_project = service.project
    projected: list[str] = []

    def project(*args, **kwargs):
        projected.append(kwargs["stock_code"])
        return original_project(*args, **kwargs)

    monkeypatch.setattr(service, "project", project)
    incremental = _producer(incremental_root, feature_service=service)
    first = _produce(incremental, initial_inputs)
    assert first.status == "published_complete"
    assert projected == ["1101", "2382"]

    projected.clear()
    revised_inputs = {**initial_inputs, "2382": _input("2382", offset=1)}
    second = _produce(incremental, revised_inputs)
    assert second.status == "published_complete"
    assert second.reused_stock_codes == ("1101",)
    assert second.recomputed_stock_codes == ("2382",)
    assert projected == ["2382"]

    full_root = tmp_path / "fresh-full"
    full_service = DailyMarketFeatureSnapshotService()
    full_projected: list[str] = []
    full_original_project = full_service.project

    def full_project(*args, **kwargs):
        full_projected.append(kwargs["stock_code"])
        return full_original_project(*args, **kwargs)

    monkeypatch.setattr(full_service, "project", full_project)
    fresh = _producer(full_root, feature_service=full_service)
    full_result = _produce(fresh, revised_inputs)
    assert full_result.status == "published_complete"
    assert full_projected == ["1101", "2382"]

    incremental_verified = DailyMarketSnapshotRepository(incremental_root).load_latest(
        cohort_id="ux19-test-cohort", decision_date=DECISION_DATE
    )
    full_verified = DailyMarketSnapshotRepository(full_root).load_latest(
        cohort_id="ux19-test-cohort", decision_date=DECISION_DATE
    )
    incremental_records = {
        item["stock_code"]: item for item in incremental_verified.manifest["stocks"]
    }
    full_records = {item["stock_code"]: item for item in full_verified.manifest["stocks"]}
    for code in ("1101", "2382"):
        assert incremental_records[code]["artifact_sha256"] == full_records[code]["artifact_sha256"]
        assert (
            incremental_records[code]["snapshot_identity_sha256"]
            == full_records[code]["snapshot_identity_sha256"]
        )
        assert incremental_verified.stock_snapshots[code] == full_verified.stock_snapshots[code]


@pytest.mark.parametrize("failure_point", ["manifest_write", "source_guard"])
def test_failed_generation_keeps_previous_latest_pointer(
    tmp_path: Path, monkeypatch, failure_point: str
):
    inputs = {"2382": _input("2382")}
    producer = _producer(tmp_path / failure_point)
    assert _produce(producer, inputs).status == "published_complete"
    previous_pointer = (producer.root / "latest.json").read_bytes()
    previous = DailyMarketSnapshotRepository(producer.root).load_latest(
        cohort_id="ux19-test-cohort", decision_date=DECISION_DATE
    )

    revised = {"2382": _input("2382", offset=1)}
    before_publish = None
    if failure_point == "manifest_write":
        original_write = producer._write_immutable

        def interrupt_after_manifest(path: Path, payload: bytes, staging_dir: Path):
            original_write(path, payload, staging_dir)
            if "manifests" in path.parts:
                raise OSError("injected interruption after immutable manifest write")

        monkeypatch.setattr(producer, "_write_immutable", interrupt_after_manifest)
    else:
        def reject_publish():
            raise RuntimeError("injected source revision during final guard")

        before_publish = reject_publish

    failed = _produce(producer, revised, before_publish=before_publish)
    assert failed.published is False
    assert failed.status in {"publish_failed", "source_changed"}
    assert (producer.root / "latest.json").read_bytes() == previous_pointer
    still_latest = DailyMarketSnapshotRepository(producer.root).load_latest(
        cohort_id="ux19-test-cohort", decision_date=DECISION_DATE
    )
    assert still_latest.manifest_sha256 == previous.manifest_sha256
    assert still_latest.stock_snapshots["2382"] == previous.stock_snapshots["2382"]


def test_corrupt_pointer_and_capacity_shortfall_fail_closed_without_publish(tmp_path: Path):
    inputs = {"2382": _input("2382")}
    root = tmp_path / "blocked"
    producer = _producer(root, capacity_probe=_capacity_probe(CANONICAL_HEAVY_CHAIN_SAFETY_RESERVE_BYTES))
    blocked = _produce(producer, inputs)
    assert blocked.status == "capacity_blocked"
    assert blocked.error_code == "capacity_reserve_unavailable"
    assert not root.exists()

    good = _producer(tmp_path / "corrupt")
    assert _produce(good, inputs).status == "published_complete"
    pointer = good.root / "latest.json"
    pointer.write_text('{"schema_version":"wrong"}', encoding="utf-8")
    corrupted_bytes = pointer.read_bytes()
    corrupt_result = _produce(good, inputs)
    assert corrupt_result.status == "prior_snapshot_invalid"
    assert pointer.read_bytes() == corrupted_bytes


def test_future_cutoff_and_source_failure_do_not_write(tmp_path: Path):
    root = tmp_path / "future"
    producer = _producer(root)
    calls: list[str] = []

    future = producer.produce(
        cohort_id="ux19-test-cohort",
        decision_cutoff=datetime(2026, 10, 5, 16, 0, 1, tzinfo=TAIPEI),
        stock_codes=("2382",),
        source_loader=lambda code, day: calls.append(code),
    )
    assert future.status == "future_decision_cutoff"
    assert calls == []
    assert not root.exists()

    source_error = producer.produce(
        cohort_id="ux19-test-cohort",
        decision_cutoff=CUTOFF,
        stock_codes=("2382",),
        source_loader=lambda _code, _day: (_ for _ in ()).throw(RuntimeError("source unavailable")),
    )
    assert source_error.status == "source_unavailable"
    assert source_error.published is False
    assert not root.exists()


def test_reentrant_same_root_instance_returns_busy(tmp_path: Path):
    root = tmp_path / "mutex"
    outer = _producer(root)
    inner = _producer(root)
    nested_results = []
    data = {"2382": _input("2382")}

    def load(stock_code: str, requested_date: date):
        assert requested_date == DECISION_DATE
        if not nested_results:
            nested_results.append(_produce(inner, data))
        return data[stock_code]

    result = outer.produce(
        cohort_id="ux19-test-cohort",
        decision_cutoff=CUTOFF,
        stock_codes=("2382",),
        source_loader=load,
    )
    assert nested_results[0].status == "busy"
    assert result.status == "published_complete"


def test_input_and_scope_bounds_are_checked_before_source_loading(tmp_path: Path):
    valid = _input("2382")
    with pytest.raises(ValueError, match="price_points"):
        DailyMarketSnapshotInput(
            stock_code="2382",
            scope_identity=valid.scope_identity,
            price_points=valid.price_points * 2 + (valid.price_points[0],),
            technical=valid.technical,
            source_refs=valid.source_refs,
        )

    producer = _producer(tmp_path / "bounds")
    called = False

    def load(_code: str, _day: date):
        nonlocal called
        called = True
        return valid

    with pytest.raises(ValueError, match="stock_codes"):
        producer.produce(
            cohort_id="ux19-test-cohort",
            decision_cutoff=CUTOFF,
            stock_codes=tuple(f"{1000 + index}" for index in range(17)),
            source_loader=load,
        )
    assert called is False
