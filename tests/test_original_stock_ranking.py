from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from typing import Any, Callable
from zoneinfo import ZoneInfo

import pytest

import app_module.original_stock_ranking as ranking_module
from app_module.daily_market_research_universe import load_research_universe_spec
from app_module.daily_market_snapshot_producer import DailyMarketSnapshotInput, DailyMarketSnapshotProducer
from app_module.daily_market_snapshot_repository import DailyMarketSnapshotRepository
from app_module.daily_market_snapshot_source import SQLiteDailyMarketSnapshotSource
from app_module.original_stock_ranking import (
    OriginalStockRankingPublisher,
    OriginalStockRankingRepository,
    OriginalStockRankingError,
)
from data_module import ml_storage_capacity


DECISION_DATE = date(2026, 10, 5)
TAIPEI = ZoneInfo("Asia/Taipei")
COHORT_ID = "original-rank-test-universe"
STOCK_CODES = ("1101", "2317", "2330")
_GIB = 1024**3


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _usage(path: Path, free: int = 300 * _GIB) -> dict[str, Any]:
    total = 500 * _GIB
    return {"probe_path": str(path), "total_bytes": total, "used_bytes": total - free, "free_bytes": free}


def _dates(count: int = 120) -> list[date]:
    values: list[date] = []
    cursor = DECISION_DATE
    while len(values) < count:
        if cursor.weekday() < 5:
            values.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(values))


def _universe_payload() -> dict[str, Any]:
    return {
        "schema_version": "daily-market-research-universe.v1",
        "universe_id": COHORT_ID,
        "version": "v1",
        "as_of_date": DECISION_DATE.isoformat(),
        "method": "daily-market-close-ma.v1",
        "included_stock_codes": list(STOCK_CODES),
        "excluded_stock_codes": [],
        "population_count": None,
        "scope": "bounded_research_cohort",
        "research_only": True,
        "complete_fixed_cohort": False,
    }


def _create_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            'CREATE TABLE daily_prices '
            '("日期" TEXT, "證券代號" TEXT, "證券名稱" TEXT, "開盤價" TEXT, '
            '"最高價" TEXT, "最低價" TEXT, "收盤價" TEXT, "成交股數" INTEGER, '
            '"成交金額" TEXT, "漲跌價差" TEXT)'
        )
        connection.execute(
            'CREATE TABLE technical_indicators '
            '("日期" TEXT, "證券代號" TEXT, "MA20" TEXT, "MA60" TEXT)'
        )
        for code in STOCK_CODES:
            for index, market_date in enumerate(_dates()):
                if code == "1101":
                    close = Decimal("4.80")
                    volume = 1000 + index
                elif code == "2317":
                    close = Decimal("180") + Decimal(index) * Decimal("0.15")
                    volume = 3000 + index * 7
                else:
                    close = Decimal("100") + Decimal(index) * Decimal("0.75")
                    volume = 1200 + index * 90
                open_price = close - Decimal("0.10")
                high = close + Decimal("0.50")
                low = close - Decimal("0.50")
                connection.execute(
                    "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        market_date.isoformat(),
                        code,
                        f"測試{code}",
                        str(open_price),
                        str(high),
                        str(low),
                        str(close),
                        volume,
                        str(close * volume),
                        "0",
                    ),
                )
            connection.execute(
                "INSERT INTO technical_indicators VALUES (?, ?, ?, ?)",
                (DECISION_DATE.isoformat(), code, "100", "95"),
            )
        connection.commit()
    finally:
        connection.close()


@pytest.fixture
def market(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    # 這只縮小測試 fixture 的來源快照 reserve；排名 writer 本身仍按 200 GiB preflight。
    import app_module.daily_market_snapshot_producer as snapshot_producer_module

    monkeypatch.setattr(snapshot_producer_module, "resolve_heavy_chain_safety_reserve", lambda _value: 1)
    monkeypatch.setattr(ml_storage_capacity, "filesystem_usage", _usage)

    config_path = tmp_path / "universe.json"
    config_path.write_bytes(_canonical(_universe_payload()))
    spec = load_research_universe_spec(config_path)
    db_path = tmp_path / "market.sqlite"
    _create_database(db_path)

    inputs: dict[str, DailyMarketSnapshotInput] = {}
    with SQLiteDailyMarketSnapshotSource(db_path, DECISION_DATE) as source:
        for code in STOCK_CODES:
            points, technical, scope_identity, refs = source.load(code)
            inputs[code] = DailyMarketSnapshotInput(
                stock_code=code,
                scope_identity=scope_identity,
                price_points=points,
                technical=technical,
                source_refs=refs,
            )

    snapshot_root = tmp_path / "feature-snapshots"
    producer = DailyMarketSnapshotProducer(
        snapshot_root,
        capacity_probe=_usage,
        reserve_bytes=1,
        clock=lambda: datetime(2026, 10, 5, 16, 0, tzinfo=TAIPEI),
    )

    def load_input(code: str, requested_date: date) -> DailyMarketSnapshotInput:
        assert requested_date == DECISION_DATE
        return inputs[code]

    produced = producer.produce(
        cohort_id=COHORT_ID,
        decision_cutoff=datetime.combine(DECISION_DATE, time(15, 0), tzinfo=TAIPEI),
        stock_codes=STOCK_CODES,
        source_loader=load_input,
        research_universe=spec,
    )
    assert produced.status == "published_complete", produced.to_dict()
    snapshot = DailyMarketSnapshotRepository(snapshot_root).load_latest(COHORT_ID, DECISION_DATE)
    return {
        "snapshot_root": snapshot_root,
        "ranking_root": tmp_path / "rankings",
        "db_path": db_path,
        "snapshot": snapshot,
        "capacity_probe": _usage,
    }


def _publisher(market: dict[str, Any]) -> OriginalStockRankingPublisher:
    return OriginalStockRankingPublisher(market["snapshot_root"], ranking_root=market["ranking_root"])


def _repository(market: dict[str, Any]) -> OriginalStockRankingRepository:
    return OriginalStockRankingRepository(market["snapshot_root"], ranking_root=market["ranking_root"])


def _publish(market: dict[str, Any], period: str = "day", direction: str = "strong") -> dict[str, Any]:
    return _publisher(market).publish(
        market["snapshot"], db_path=market["db_path"], period=period, direction=direction
    )


def _read(market: dict[str, Any], period: str = "day", direction: str = "strong"):
    return _repository(market).read(
        market["snapshot"], db_path=market["db_path"], period=period, direction=direction
    )


def _ranking_pointer(market: dict[str, Any], period: str = "day", direction: str = "strong") -> Path:
    return market["ranking_root"] / f"latest-{period}-{direction}.json"


def test_import_is_light_and_does_not_load_legacy_engine() -> None:
    code = (
        "import sys; import app_module.original_stock_ranking; "
        "assert 'pandas' not in sys.modules; "
        "assert 'decision_module.stock_screener' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", code], check=True, cwd=Path(__file__).resolve().parents[1])


@pytest.mark.parametrize(("period", "direction"), [("day", "strong"), ("week", "weak")])
def test_publishes_actual_legacy_engine_rows_and_reads_them_back(
    market: dict[str, Any], period: str, direction: str
) -> None:
    result = _publish(market, period, direction)
    assert result["status"] == "published"

    ranking = _read(market, period, direction)
    assert ranking.readiness == "research_only"
    assert ranking.decision_date == DECISION_DATE.isoformat()
    assert ranking.eligible_universe_size == 2
    assert ranking.declared_stock_codes == STOCK_CODES
    assert ranking.missing_rank_stock_codes == ("1101",)
    assert tuple(row["rank"] for row in ranking.rows) == (1, 2)
    assert all(row["score_label"].startswith("Top ") for row in ranking.rows) if direction == "strong" else all(
        row["score_label"].startswith("Bottom ") for row in ranking.rows
    )
    assert all(row["latest_date"] == DECISION_DATE.isoformat() for row in ranking.rows)
    assert ranking.metadata["native_score_semantics"] == "legacy_percentile_label_preserved"
    assert ranking.metadata["numeric_score_status"] == "not_exposed_by_legacy_engine"
    assert ranking.metadata["parent_manifest_sha256"] == market["snapshot"].manifest_sha256
    assert ranking.metadata["engine_method"] == "StockScreener._build_stock_screen_from_frame"
    assert ranking.metadata["volume_window_size"] == 20


def test_same_verified_inputs_are_unchanged_without_engine_recompute(
    market: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _publish(market)
    assert first["status"] == "published"
    pointer_before = _ranking_pointer(market).read_bytes()

    from decision_module.stock_screener import StockScreener

    monkeypatch.setattr(StockScreener, "_build_stock_screen_from_frame", lambda *_args: pytest.fail("engine reran"))
    second = _publish(market)
    assert second["status"] == "unchanged"
    assert second["manifest_sha256"] == first["manifest_sha256"]
    assert _ranking_pointer(market).read_bytes() == pointer_before


def _rewrite_bundle(
    market: dict[str, Any],
    mutate: Callable[[dict[str, Any], dict[str, Any]], None],
    *,
    rehash_artifact: bool = True,
) -> None:
    pointer_path = _ranking_pointer(market)
    pointer = json.loads(pointer_path.read_bytes())
    manifest_path = market["ranking_root"] / ranking_module._manifest_relpath(pointer["manifest_sha256"])
    manifest = json.loads(manifest_path.read_bytes())
    artifact_path = market["ranking_root"] / ranking_module._object_relpath(manifest["artifact_sha256"])
    artifact = json.loads(artifact_path.read_bytes())
    mutate(manifest, artifact)
    if rehash_artifact:
        artifact_raw = _canonical(artifact)
        artifact_sha = hashlib.sha256(artifact_raw).hexdigest()
        manifest["artifact_sha256"] = artifact_sha
        artifact_path = market["ranking_root"] / ranking_module._object_relpath(artifact_sha)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(artifact_raw)
    else:
        artifact_path.write_bytes(_canonical(artifact))
        return
    manifest["manifest_identity_sha256"] = ranking_module._identity_sha256(manifest)
    manifest_raw = _canonical(manifest)
    manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
    manifest_path = market["ranking_root"] / ranking_module._manifest_relpath(manifest_sha)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(manifest_raw)
    pointer["manifest_sha256"] = manifest_sha
    pointer_path.write_bytes(_canonical(pointer))


@pytest.mark.parametrize(
    ("mutate", "rehash_artifact", "expected_code"),
    [
        (lambda _manifest, artifact: artifact["rows"][1].update(stock_code=artifact["rows"][0]["stock_code"]), True, "ranking_row_scope_invalid"),
        (lambda _manifest, artifact: artifact["rows"][0].update(latest_date="2026-10-02"), True, "ranking_row_date_mismatch"),
        (lambda manifest, _artifact: manifest.update(schema_version="old.version"), True, "ranking_manifest_schema_mismatch"),
        (lambda manifest, _artifact: manifest["engine"].update(method="Other.method"), True, "ranking_manifest_binding_mismatch"),
        (lambda manifest, _artifact: manifest["engine"].update(version="old.engine"), True, "ranking_manifest_binding_mismatch"),
        (lambda manifest, _artifact: manifest["engine_parameters"].update(top_n=2), True, "ranking_manifest_binding_mismatch"),
        (lambda manifest, _artifact: manifest["research_universe"].update(universe_id="other-universe"), True, "ranking_manifest_binding_mismatch"),
        (lambda _manifest, artifact: artifact["rows"][0].update(latest_date="2026-10-02"), False, "ranking_artifact_hash_mismatch"),
        (lambda manifest, _artifact: manifest.update(eligible_universe_size=True), True, "ranking_eligible_count_mismatch"),
    ],
)
def test_reader_rejects_duplicate_incompatible_date_hash_and_bool_alias(
    market: dict[str, Any], mutate, rehash_artifact: bool, expected_code: str
) -> None:
    assert _publish(market)["status"] == "published"
    _rewrite_bundle(market, mutate, rehash_artifact=rehash_artifact)
    with pytest.raises(OriginalStockRankingError) as error:
        _read(market)
    assert error.value.code == expected_code


def test_source_change_and_interrupted_replace_preserve_existing_pointer(
    market: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _publish(market)["status"] == "published"
    pointer_path = _ranking_pointer(market)
    original_pointer = pointer_path.read_bytes()

    _revise_source(market)
    changed = _publish(market)
    assert changed["status"] == "unavailable"
    assert changed["code"] == "ranking_source_input_hash_mismatch"
    assert pointer_path.read_bytes() == original_pointer


def _revise_source(market: dict[str, Any]) -> None:
    connection = sqlite3.connect(market["db_path"])
    try:
        connection.execute(
            'UPDATE daily_prices SET "收盤價" = "999.00", "最高價" = "999.50" '
            'WHERE "證券代號" = ? AND "日期" = ?',
            ("2330", DECISION_DATE.isoformat()),
        )
        connection.commit()
    finally:
        connection.close()


def test_cooperative_cancellation_preserves_pointer(market: dict[str, Any]) -> None:
    assert _publish(market)["status"] == "published"
    pointer_path = _ranking_pointer(market)
    original_pointer = pointer_path.read_bytes()
    result = _publisher(market).publish(
        market["snapshot"],
        db_path=market["db_path"],
        period="week",
        direction="weak",
        cancel_callback=lambda: True,
    )
    assert result["status"] == "cancelled"
    assert pointer_path.read_bytes() == original_pointer
    assert not _ranking_pointer(market, "week", "weak").exists()


def test_final_false_cancellation_callback_still_rechecks_changed_source(
    market: dict[str, Any]
) -> None:
    assert _publish(market)["status"] == "published"
    calls = 0

    def observe_only() -> bool:
        nonlocal calls
        calls += 1
        return False

    baseline = _publisher(market).publish(
        market["snapshot"],
        db_path=market["db_path"],
        period="week",
        direction="weak",
        cancel_callback=observe_only,
    )
    assert baseline["status"] == "published"
    final_callback_count = calls
    week_pointer = _ranking_pointer(market, "week", "weak")
    week_pointer.unlink()
    day_pointer_before = _ranking_pointer(market).read_bytes()
    calls = 0
    changed = False

    def revise_at_final_callback() -> bool:
        nonlocal calls, changed
        calls += 1
        if calls == final_callback_count and not changed:
            _revise_source(market)
            changed = True
        return False

    result = _publisher(market).publish(
        market["snapshot"],
        db_path=market["db_path"],
        period="week",
        direction="weak",
        cancel_callback=revise_at_final_callback,
    )
    assert changed
    assert result["status"] == "unavailable"
    assert result["code"] in {"ranking_source_changed", "ranking_source_input_hash_mismatch"}
    assert not week_pointer.exists()
    assert _ranking_pointer(market).read_bytes() == day_pointer_before


def test_busy_trigger_can_retry_after_existing_writer_releases_lock(market: dict[str, Any]) -> None:
    from app_module.daily_market_snapshot_producer import _producer_lock

    with _producer_lock(market["ranking_root"]) as acquired:
        assert acquired
        busy = _publish(market, period="week", direction="strong")
        assert busy["status"] == "unavailable"
        assert busy["code"] == "ranking_publish_busy"
        assert not _ranking_pointer(market, "week", "strong").exists()
    retried = _publish(market, period="week", direction="strong")
    assert retried["status"] == "published"


def test_interrupted_atomic_replace_keeps_existing_pointer(
    market: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _publish(market)["status"] == "published"
    pointer_path = _ranking_pointer(market)
    original_pointer = pointer_path.read_bytes()
    interrupted_pointer = _ranking_pointer(market, "week", "strong")
    replace = os.replace

    def fail_pointer_replace(source: Any, destination: Any) -> None:
        if Path(destination) == interrupted_pointer:
            raise OSError("simulated interrupted pointer publish")
        replace(source, destination)

    monkeypatch.setattr(ranking_module.os, "replace", fail_pointer_replace)
    result = _publish(market, period="week", direction="strong")
    assert result["status"] == "unavailable"
    assert not _ranking_pointer(market, "week", "strong").exists()
    assert pointer_path.read_bytes() == original_pointer
    assert not list(market["ranking_root"].glob(".latest-week-strong.json.*.tmp"))


def test_low_price_stock_is_explicitly_missing_from_native_rank(market: dict[str, Any]) -> None:
    assert _publish(market)["status"] == "published"
    ranking = _read(market)
    assert ranking.missing_rank_stock_codes == ("1101",)
    assert ranking.metadata["missing_rank_reason"]["1101"] == "native_engine_rejection_reason_unavailable"


def test_capacity_block_leaves_pointer_unpublished(market: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ml_storage_capacity, "filesystem_usage", lambda path: _usage(path, free=199 * _GIB))
    result = _publish(market)
    assert result["status"] == "unavailable"
    assert result["code"] == "ranking_capacity_blocked"
    assert not _ranking_pointer(market).exists()


def test_read_does_not_call_legacy_engine_builder(market: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    assert _publish(market)["status"] == "published"
    from decision_module.stock_screener import StockScreener

    monkeypatch.setattr(StockScreener, "_build_stock_screen_from_frame", lambda *_args: pytest.fail("reader invoked engine"))
    assert _read(market).eligible_universe_size == 2


def test_operating_system_lock_releases_after_hard_process_exit(tmp_path: Path) -> None:
    root = tmp_path / "lock-root"
    child = (
        "import os, sys; from pathlib import Path; "
        "from app_module.daily_market_snapshot_producer import _producer_lock; "
        "ctx = _producer_lock(Path(sys.argv[1])); acquired = ctx.__enter__(); "
        "print('locked' if acquired else 'busy', flush=True); os._exit(0)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", child, str(root)], check=True, capture_output=True, text=True, timeout=15
    )
    assert completed.stdout.strip() == "locked"

    from app_module.daily_market_snapshot_producer import _producer_lock

    with _producer_lock(root) as acquired:
        assert acquired
