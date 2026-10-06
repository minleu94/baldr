from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import pytest

from app_module.daily_market_research_screener import DailyMarketResearchScreenerService
from app_module.daily_market_research_universe import (
    ResearchUniverseContractError,
    load_research_universe_spec,
)
from app_module.daily_market_snapshot_producer import (
    DailyMarketSnapshotInput,
    DailyMarketSnapshotProducer,
)
from app_module.daily_market_snapshot_repository import (
    DailyMarketSnapshotRepository,
    DailyMarketSnapshotVerificationError,
    canonical_snapshot_json_bytes,
    cohort_identity_sha256,
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


def _payload(
    *,
    version: str = "v1",
    as_of_date: str = DECISION_DATE.isoformat(),
    included: tuple[str, ...] = ("2317", "2330"),
    excluded: tuple[tuple[str, str], ...] = (("2382", "manual_review_scope_limit"),),
    population_count: int | None = None,
    complete_fixed_cohort: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": "daily-market-research-universe.v1",
        "universe_id": "ux16-candidate-set",
        "version": version,
        "as_of_date": as_of_date,
        "method": "daily-market-close-ma.v1",
        "included_stock_codes": list(included),
        "excluded_stock_codes": [
            {"stock_code": code, "reason": reason} for code, reason in excluded
        ],
        "population_count": population_count,
        "scope": "bounded_research_cohort",
        "research_only": True,
        "complete_fixed_cohort": complete_fixed_cohort,
    }


def _write_config(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_bytes(
        json.dumps(
            dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )


def _capacity_probe(
    free_bytes: int = CANONICAL_HEAVY_CHAIN_SAFETY_RESERVE_BYTES + 4 * 1024**3,
):
    total_bytes = free_bytes + 32 * 1024**3

    def probe(path: Path) -> Mapping[str, Any]:
        return {
            "probe_path": str(path),
            "total_bytes": total_bytes,
            "used_bytes": total_bytes - free_bytes,
            "free_bytes": free_bytes,
        }

    return probe


def _price_points(stock_code: str, *, offset: int = 0) -> tuple[StockPricePointDTO, ...]:
    dates: list[date] = []
    cursor = DECISION_DATE
    while len(dates) < 60:
        if cursor.weekday() < 5:
            dates.append(cursor)
        cursor -= timedelta(days=1)
    dates.reverse()
    rows: list[StockPricePointDTO] = []
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
                source_snapshot_hash=f"{stock_code}-price-{index:03d}-{offset}",
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


def _loader(inputs: Mapping[str, DailyMarketSnapshotInput]):
    def load(stock_code: str, requested_date: date) -> DailyMarketSnapshotInput:
        assert requested_date == DECISION_DATE
        return inputs[stock_code]

    return load


def _producer(
    root: Path,
    *,
    free_bytes: int = CANONICAL_HEAVY_CHAIN_SAFETY_RESERVE_BYTES + 4 * 1024**3,
) -> DailyMarketSnapshotProducer:
    return DailyMarketSnapshotProducer(
        root,
        capacity_probe=_capacity_probe(free_bytes),
        clock=lambda: CLOCK_NOW,
    )


def _produce(
    root: Path,
    spec_path: Path,
    *,
    inputs: Mapping[str, DailyMarketSnapshotInput] | None = None,
    before_publish=None,
):
    spec = load_research_universe_spec(spec_path)
    source_inputs = inputs or {code: _input(code) for code in spec.included_stock_codes}
    return _producer(root).produce(
        cohort_id=spec.universe_id,
        decision_cutoff=CUTOFF,
        stock_codes=spec.included_stock_codes,
        source_loader=_loader(source_inputs),
        before_publish=before_publish,
        research_universe=spec,
    )


def _repin_latest(root: Path, mutate) -> None:
    pointer_path = root / "latest.json"
    pointer = json.loads(pointer_path.read_bytes())
    old_sha = pointer["manifest_sha256"]
    manifest_path = root / snapshot_manifest_relpath(old_sha)
    manifest = json.loads(manifest_path.read_bytes())
    mutate(manifest)
    manifest["manifest_identity_sha256"] = snapshot_manifest_identity_sha256(manifest)
    raw = canonical_snapshot_json_bytes(manifest)
    digest = hashlib.sha256(raw).hexdigest()
    (root / snapshot_manifest_relpath(digest)).write_bytes(raw)
    pointer_path.write_bytes(
        canonical_snapshot_json_bytes(
            {"schema_version": pointer["schema_version"], "manifest_sha256": digest}
        )
    )


def test_configured_snapshot_binds_included_members_and_unknown_denominator(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "universe.json"
    _write_config(config_path, _payload(population_count=None))
    spec = load_research_universe_spec(config_path)
    result = _produce(tmp_path / "snapshot", config_path)

    assert result.status == "published_complete"
    assert tuple(result.declared_stock_codes) == spec.included_stock_codes
    assert result.reused_stock_codes == ()
    verified = DailyMarketSnapshotRepository(tmp_path / "snapshot").load_latest(
        spec.universe_id, DECISION_DATE
    )
    binding = verified.manifest["research_universe"]
    assert binding == spec.to_manifest_binding()
    assert binding["population_count"] is None
    assert binding["included_stock_codes"] == ["2317", "2330"]
    assert binding["excluded_stock_codes"] == [
        {"stock_code": "2382", "reason": "manual_review_scope_limit"}
    ]
    assert verified.manifest_identity_sha256 == verified.manifest[
        "manifest_identity_sha256"
    ]


def test_reader_preserves_extensionless_v2_as_legacy_declared_research_only(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "legacy"
    inputs = {code: _input(code) for code in ("2317", "2330")}
    result = _producer(output_root).produce(
        cohort_id="legacy-cohort",
        decision_cutoff=CUTOFF,
        stock_codes=("2317", "2330"),
        source_loader=_loader(inputs),
    )
    assert result.status == "published_complete"
    verified = DailyMarketSnapshotRepository(output_root).load_latest(
        "legacy-cohort", DECISION_DATE
    )
    assert "research_universe" not in verified.manifest

    service = DailyMarketResearchScreenerService(
        SimpleNamespace(db_file=tmp_path / "unused.sqlite"), snapshot_root=output_root
    )
    rows = service.filter_rows(verified, ("close_above_ma20",), "AND")
    assert {row.research_universe_membership for row in rows} == {
        "legacy_declared_research_only"
    }
    assert all(row.research_universe is None for row in rows)
    assert all(row.original_rank is None for row in rows)
    assert all(
        row.original_rank_unknown_reason == "original_rank_immutable_source_missing"
        for row in rows
    )


def test_membership_and_version_changes_force_full_rebuild_without_reuse(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "universe.json"
    output_root = tmp_path / "snapshot"
    _write_config(config_path, _payload(population_count=3, complete_fixed_cohort=True))
    first = _produce(output_root, config_path)
    assert first.status == "published_complete"
    first_manifest_sha = first.manifest_sha256

    manual_calls: list[str] = []

    def manual_loader(code: str, requested_date: date) -> DailyMarketSnapshotInput:
        manual_calls.append(code)
        return _input(code)

    manual_result = _producer(output_root).produce(
        cohort_id="manual-cohort-override",
        decision_cutoff=CUTOFF,
        stock_codes=("2330",),
        source_loader=manual_loader,
    )
    assert manual_result.status == "research_universe_config_required"
    assert manual_result.error_code == "snapshot_research_universe_config_required"
    assert manual_calls == []

    version_payload = _payload(version="v2", population_count=3, complete_fixed_cohort=True)
    _write_config(config_path, version_payload)
    version_spec = load_research_universe_spec(config_path)
    with pytest.raises(DailyMarketSnapshotVerificationError) as changed_source:
        DailyMarketSnapshotRepository(output_root).load_latest(
            version_spec.universe_id, DECISION_DATE
        )
    assert changed_source.value.code == "snapshot_research_universe_source_changed"

    version_result = _produce(output_root, config_path)
    assert version_result.status == "published_complete"
    assert version_result.reused_stock_codes == ()
    assert version_result.recomputed_stock_codes == version_spec.included_stock_codes
    assert version_result.manifest_sha256 != first_manifest_sha

    membership_payload = _payload(
        version="v3",
        included=("2330", "2382"),
        excluded=(("2317", "manual_review_scope_limit"),),
        population_count=3,
        complete_fixed_cohort=True,
    )
    _write_config(config_path, membership_payload)
    membership_spec = load_research_universe_spec(config_path)
    membership_result = _produce(
        output_root,
        config_path,
        inputs={code: _input(code) for code in membership_spec.included_stock_codes},
    )
    assert membership_result.status == "published_complete"
    assert membership_result.reused_stock_codes == ()
    assert membership_result.recomputed_stock_codes == ("2330", "2382")
    assert membership_result.declared_stock_codes == ("2330", "2382")

    config_path.unlink()
    with pytest.raises(DailyMarketSnapshotVerificationError) as missing_source:
        DailyMarketSnapshotRepository(output_root).load_latest(
            membership_spec.universe_id, DECISION_DATE
        )
    assert missing_source.value.code == "snapshot_research_universe_source_missing"


def test_config_file_change_before_publish_keeps_previous_latest_pointer(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "universe.json"
    output_root = tmp_path / "snapshot"
    _write_config(config_path, _payload(population_count=None))
    first = _produce(output_root, config_path)
    assert first.status == "published_complete"
    pointer_path = output_root / "latest.json"
    old_pointer = pointer_path.read_bytes()
    spec = load_research_universe_spec(config_path)

    def change_config() -> None:
        _write_config(config_path, _payload(version="v2", population_count=None))

    result = _producer(output_root).produce(
        cohort_id=spec.universe_id,
        decision_cutoff=CUTOFF,
        stock_codes=spec.included_stock_codes,
        source_loader=_loader(
            {code: _input(code, offset=1) for code in spec.included_stock_codes}
        ),
        before_publish=change_config,
        research_universe=spec,
    )
    assert result.status == "source_changed"
    assert pointer_path.read_bytes() == old_pointer


@pytest.mark.parametrize(
    "change",
    (
        lambda config: config.update(included_stock_codes=["2317", "2317"]),
        lambda config: config.update(as_of_date="2026-02-30"),
        lambda config: config.update(population_count=99, complete_fixed_cohort=True),
    ),
    ids=("duplicate-member", "date", "denominator"),
)
def test_invalid_config_is_rejected_before_any_source_call(
    tmp_path: Path, change
) -> None:
    payload = _payload(population_count=3, complete_fixed_cohort=True)
    change(payload)
    config_path = tmp_path / "universe.json"
    _write_config(config_path, payload)
    with pytest.raises(ResearchUniverseContractError):
        load_research_universe_spec(config_path)


def test_producer_rejects_config_as_of_date_different_from_cutoff(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "universe.json"
    _write_config(config_path, _payload(as_of_date="2026-10-04"))
    spec = load_research_universe_spec(config_path)
    calls: list[str] = []

    def source_loader(code: str, requested_date: date) -> DailyMarketSnapshotInput:
        calls.append(code)
        return _input(code)

    with pytest.raises(ValueError, match="as_of_date"):
        _producer(tmp_path / "snapshot").produce(
            cohort_id=spec.universe_id,
            decision_cutoff=CUTOFF,
            stock_codes=spec.included_stock_codes,
            source_loader=source_loader,
            research_universe=spec,
        )
    assert calls == []


def test_manifest_rejects_null_extension_hash_tampering_and_membership_mismatch(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "universe.json"
    output_root = tmp_path / "snapshot"
    _write_config(config_path, _payload(population_count=None))
    spec = load_research_universe_spec(config_path)
    _produce(output_root, config_path)
    repository = DailyMarketSnapshotRepository(output_root)

    _repin_latest(output_root, lambda manifest: manifest.update(research_universe=None))
    with pytest.raises(DailyMarketSnapshotVerificationError) as null_extension:
        repository.load_latest(spec.universe_id, DECISION_DATE)
    assert null_extension.value.code == "snapshot_research_universe_binding_invalid"

    # Restore a valid latest snapshot, then re-pin independent semantic tampering.
    output_root = tmp_path / "snapshot-after-null"
    _produce(output_root, config_path)
    repository = DailyMarketSnapshotRepository(output_root)

    def change_hash(manifest: dict[str, Any]) -> None:
        manifest["research_universe"]["source_sha256"] = "0" * 64

    _repin_latest(output_root, change_hash)
    with pytest.raises(DailyMarketSnapshotVerificationError) as bad_hash:
        repository.load_latest(spec.universe_id, DECISION_DATE)
    assert bad_hash.value.code == "snapshot_research_universe_source_changed"

    output_root = tmp_path / "snapshot-after-hash"
    _produce(output_root, config_path)
    repository = DailyMarketSnapshotRepository(output_root)

    def change_membership(manifest: dict[str, Any]) -> None:
        declared = ["2317", "2330", "2382"]
        manifest["declared_stock_codes"] = declared
        manifest["cohort_identity"] = cohort_identity_sha256(
            str(manifest["cohort_id"]), declared
        )

    _repin_latest(output_root, change_membership)
    with pytest.raises(DailyMarketSnapshotVerificationError) as wrong_membership:
        repository.load_latest(spec.universe_id, DECISION_DATE)
    assert wrong_membership.value.code == "snapshot_research_universe_membership_mismatch"


def test_configured_producer_rejects_manual_membership_and_cohort_overrides(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "universe.json"
    _write_config(config_path, _payload(population_count=None))
    spec = load_research_universe_spec(config_path)
    service = DailyMarketResearchScreenerService(
        SimpleNamespace(db_file=tmp_path / "unused.sqlite"),
        snapshot_root=tmp_path / "snapshot",
        universe_config_path=config_path,
    )

    with pytest.raises(ValueError, match="included members"):
        service.produce_snapshot(("2317",), CUTOFF, spec.universe_id)
    with pytest.raises(ValueError, match="universe_id"):
        service.produce_snapshot(
            spec.included_stock_codes, CUTOFF, "manual-cohort-override"
        )


def test_configured_producer_preserves_two_hundred_gibibyte_reserve_gate(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "universe.json"
    _write_config(
        config_path,
        _payload(
            included=("2330",),
            excluded=(),
            population_count=None,
            complete_fixed_cohort=False,
        ),
    )
    spec = load_research_universe_spec(config_path)
    free_bytes = CANONICAL_HEAVY_CHAIN_SAFETY_RESERVE_BYTES - 1
    total_bytes = free_bytes + 10 * 1024**3

    def low_capacity_probe(path: Path) -> Mapping[str, Any]:
        return {
            "probe_path": str(path),
            "total_bytes": total_bytes,
            "used_bytes": total_bytes - free_bytes,
            "free_bytes": free_bytes,
        }

    producer = DailyMarketSnapshotProducer(
        tmp_path / "capacity-blocked",
        capacity_probe=low_capacity_probe,
        clock=lambda: CLOCK_NOW,
    )
    result = producer.produce(
        cohort_id=spec.universe_id,
        decision_cutoff=CUTOFF,
        stock_codes=spec.included_stock_codes,
        source_loader=_loader({"2330": _input("2330")}),
        research_universe=spec,
    )
    assert result.status == "capacity_blocked"
    assert result.capacity_preflight.get("safety_reserve_bytes") == (
        CANONICAL_HEAVY_CHAIN_SAFETY_RESERVE_BYTES
    )
    assert not (tmp_path / "capacity-blocked" / "latest.json").exists()


def test_universe_config_rejects_more_than_sixteen_included_members(
    tmp_path: Path,
) -> None:
    codes = tuple(f"{code:04d}" for code in range(1000, 1017))
    config_path = tmp_path / "universe.json"
    _write_config(
        config_path,
        _payload(
            included=codes,
            excluded=(),
            population_count=None,
            complete_fixed_cohort=False,
        ),
    )
    with pytest.raises(ResearchUniverseContractError):
        load_research_universe_spec(config_path)
