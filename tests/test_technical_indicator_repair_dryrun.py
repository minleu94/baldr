from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.technical_indicator_repair_dryrun import (
    DEPENDENT_INDICATORS,
    DryRunError,
    _load_overlay,
    _source_copy_plan,
    _compute_segmented,
    run_dryrun,
)
from scripts.technical_indicator_repair_apply_guard import (
    ApplyGuardError,
    build_apply_plan,
)
from scripts import technical_indicator_repair_apply_guard as apply_guard


def _business_dates() -> list[str]:
    before = list(pd.bdate_range(end="2026-05-20", periods=60))
    after = list(pd.bdate_range(start="2026-05-20", periods=40))[1:]
    return [item.strftime("%Y%m%d") for item in before + after]


def _make_fixture_db(path: Path) -> tuple[list[str], dict[str, dict[str, object]]]:
    dates = _business_dates()
    dependent_sql = ",\n        ".join(f'"{column}" REAL' for column in DEPENDENT_INDICATORS)
    connection = sqlite3.connect(path)
    connection.execute(
        f'''CREATE TABLE daily_prices (
            "日期" TEXT NOT NULL,
            "證券代號" TEXT NOT NULL,
            "開盤價" REAL,
            "最高價" REAL,
            "最低價" REAL,
            "收盤價" REAL,
            "成交股數" INTEGER,
            PRIMARY KEY ("日期", "證券代號")
        )'''
    )
    connection.execute(
        f'''CREATE TABLE technical_indicators (
            "日期" TEXT NOT NULL,
            "證券代號" TEXT NOT NULL,
            {dependent_sql},
            "ATR" REAL,
            "UNKNOWN_COLUMN" TEXT,
            PRIMARY KEY ("日期", "證券代號")
        )'''
    )
    canonical: dict[str, dict[str, object]] = {}
    for symbol, missing_target in (("1001", False), ("2002", True)):
        for index, key in enumerate(dates):
            close = 80.0 + index * 0.75 + (0.5 if symbol == "2002" else 0.0)
            connection.execute(
                'INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?)',
                (key, symbol, close - 0.5, close + 1.0, close - 1.0, close, 1000 + index),
            )
        target_index = dates.index("20260520")
        if missing_target:
            canonical[symbol] = {
                "symbol": symbol,
                "date": "20260520",
                "open": None,
                "high": None,
                "low": None,
                "close": None,
                "volume_shares": "1200",
                "turnover": "100000",
                "change_value": "0.0",
                "sign": None,
            }
        else:
            canonical[symbol] = {
                "symbol": symbol,
                "date": "20260520",
                "open": "125.0",
                "high": "127.0",
                "low": "123.0",
                "close": "126.0",
                "volume_shares": "2200",
                "turnover": "277200",
                "change_value": "1.0",
                "sign": "+",
            }
        # Existing technical rows begin at target. The value 1.0 makes both
        # replacement and NULL invalidation visible in the manifest.
        for key in dates[target_index:]:
            values = [key, symbol, *([1.0] * len(DEPENDENT_INDICATORS)), 77.0, "preserve"]
            connection.execute(
                f'INSERT INTO technical_indicators VALUES ({",".join("?" for _ in values)})',
                values,
            )
    connection.commit()
    connection.close()
    return dates, canonical


def _write_overlay(path: Path, canonical: dict[str, dict[str, object]]) -> None:
    rows = [
        {"symbol": symbol, "date": "20260520", "canonical_daily_csv": row}
        for symbol, row in canonical.items()
    ]
    path.write_text(
        json.dumps(
            {
                "schema_version": "fixture",
                "comparisons": {
                    "sqlite_vs_canonical_daily_csv": {"mismatch_rows": rows}
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_segmented_talib_resets_warmup_after_missing_ohlc() -> None:
    rows = []
    for index in range(80):
        close = 100.0 + index
        rows.append(
            {
                "date": f"{index:08d}",
                "symbol": "1001",
                "open": close - 0.5,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1000,
            }
        )
    rows[40]["close"] = np.nan
    rows[40]["open"] = np.nan
    frame = pd.DataFrame(rows)
    result = _compute_segmented(frame)

    assert pd.notna(result.loc[39, "SMA30"])
    assert result.loc[40, list(DEPENDENT_INDICATORS)].isna().all()
    # Each kernel warms up from the segment boundary; long-window values
    # remain NULL while short-window kernels become available independently.
    assert result.loc[41:69, ["SMA30", "DEMA30", "EMA30", "MA60"]].isna().all().all()
    assert pd.notna(result.loc[46, "MA5"])
    assert pd.notna(result.loc[70, "SMA30"])


def test_dryrun_keeps_missing_target_symbol_and_only_plans_existing_rows(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    db_path = data_root / "sqlite" / "twstock.db"
    db_path.parent.mkdir(parents=True)
    _dates, canonical = _make_fixture_db(db_path)
    overlay_path = tmp_path / "overlay.json"
    _write_overlay(overlay_path, canonical)
    output_path = tmp_path / "qa" / "dryrun.json"

    before = db_path.read_bytes()
    manifest = run_dryrun(
        db_path=db_path,
        overlay_path=overlay_path,
        output_path=output_path,
        data_root=data_root,
        symbols=["1001", "2002"],
    )
    after = db_path.read_bytes()

    assert before == after
    assert manifest["read_only"]["formal_data_written"] is False
    assert manifest["summary"]["planned_symbols"] == 2
    assert manifest["summary"]["updated_rows"] > 0
    assert manifest["summary"]["invalidated_rows"] > 0
    assert output_path.is_file()
    assert output_path.with_suffix(".json.sha256").is_file()

    plans = {item["symbol"]: item for item in manifest["plans"]}
    missing_plan = plans["2002"]
    target_update = next(item for item in missing_plan["updates"] if item["date"] == "20260520")
    assert target_update["action"] == "invalidate_dependent_indicators"
    assert all(value is None for value in target_update["new"].values())
    assert missing_plan["technical_table"]["pre_target_rows_untouched"] is True
    assert missing_plan["technical_table"]["unknown_columns_untouched"] is True
    assert missing_plan["source_summary"]["canonical_ohlc_complete"] is False

    complete_plan = plans["1001"]
    assert all(item["date"] >= "20260520" for item in complete_plan["updates"])
    assert any(
        item["action"] == "replace_recomputed_indicators"
        for item in complete_plan["updates"]
    )


def test_dryrun_rejects_output_inside_formal_data_root(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    db_path = data_root / "sqlite" / "twstock.db"
    db_path.parent.mkdir(parents=True)
    _dates, canonical = _make_fixture_db(db_path)
    overlay_path = tmp_path / "overlay.json"
    _write_overlay(overlay_path, canonical)

    with pytest.raises(DryRunError, match="正式來源"):
        run_dryrun(
            db_path=db_path,
            overlay_path=overlay_path,
            output_path=data_root / "technical_analysis" / "manifest.json",
            data_root=data_root,
            symbols=["1001"],
        )


def test_overlay_prefers_complete_price_plan_source_schema(tmp_path: Path) -> None:
    path = tmp_path / "price_plan.json"
    path.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "symbol": "1001",
                        "date": "2026-05-20",
                        "source": {
                            "證券代號": "1001",
                            "日期": "2026-05-20",
                            "開盤價": "125.0",
                            "最高價": "127.0",
                            "最低價": "123.0",
                            "收盤價": "126.0",
                            "成交股數": "2200",
                            "成交筆數": "22",
                            "成交金額": "277200",
                            "漲跌(+/-)": "+",
                            "漲跌價差": "1.0",
                            "最後揭示買價": "125.5",
                            "最後揭示買量": "10",
                            "最後揭示賣價": "126.0",
                            "最後揭示賣量": "12",
                            "本益比": "20.0",
                        },
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    overlay, metadata = _load_overlay(path, "20260520")

    assert overlay["1001"]["open"] == "125.0"
    assert overlay["1001"]["trade_count"] == "22"
    assert overlay["1001"]["best_ask_volume"] == "12"
    assert metadata["row_schema_counts"] == {"price_repair_plan_rows_source": 1}


def test_source_copy_plan_keeps_duplicate_physical_columns_explicit() -> None:
    plan = _source_copy_plan(
        columns=["日期", "證券代號", "漲跌", "漲跌", "收盤價"],
        technical_rows=[("20260520", "1001", "+", "+", 100.0)],
        canonical={
            "symbol": "1001",
            "date": "20260520",
            "sign": "-",
            "close": "101.0",
        },
        target_date="20260520",
        source_update_columns=["漲跌", "收盤價"],
        source_plan_hash="sha256:test",
    )

    assert plan["status"] == "ready"
    assert [item["column_ordinal"] for item in plan["updates"] if item["column"] == "漲跌"] == [0, 1]
    assert any(
        item["column"] == "收盤價" and item["new"] == "101.0"
        for item in plan["updates"]
    )


def _write_price_plan(path: Path, canonical: dict[str, dict[str, object]]) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "historical-price-spike-repair-test",
                "source_date": "20260520",
                "plan_hash": "sha256:test-plan",
                "allowlist_hash": "sha256:test-allowlist",
                "canonical_sha256": "sha256:test-canonical",
                "apply_allowed": False,
                "source_update_columns": ["收盤價"],
                "rows": [
                    {"symbol": symbol, "date": "20260520", "source": row}
                    for symbol, row in canonical.items()
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_apply_guard_emits_plan_only_and_rejects_stale_manifest(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    db_path = data_root / "sqlite" / "twstock.db"
    db_path.parent.mkdir(parents=True)
    _dates, canonical = _make_fixture_db(db_path)
    price_plan = tmp_path / "price_plan.json"
    _write_price_plan(price_plan, canonical)
    manifest_path = tmp_path / "dryrun.json"
    run_dryrun(
        db_path=db_path,
        overlay_path=price_plan,
        output_path=manifest_path,
        data_root=data_root,
        symbols=["1001", "2002"],
    )

    output_path = tmp_path / "apply_guard.json"
    result = build_apply_plan(
        dryrun_manifest_path=manifest_path,
        price_plan_path=price_plan,
        output_path=output_path,
    )
    assert result["apply_allowed"] is False
    assert result["formal_data_written"] is False
    assert result["summary"]["technical_indicator_cells"] > 0
    assert result["summary"]["csv_cache_write"] is False
    assert output_path.is_file()

    price_plan.write_text(price_plan.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ApplyGuardError, match="file hash 已過期"):
        build_apply_plan(
            dryrun_manifest_path=manifest_path,
            price_plan_path=price_plan,
        )


def _write_fixture_price_plan(
    path: Path,
    db_path: Path,
    canonical: dict[str, dict[str, object]],
) -> None:
    def raw_source(row: dict[str, object]) -> dict[str, object]:
        """Mirror the verified price-plan source shape used by production."""
        return {
            "證券代號": row["symbol"],
            "日期": row["date"],
            "開盤價": row["open"],
            "最高價": row["high"],
            "最低價": row["low"],
            "收盤價": row["close"],
            "成交股數": row["volume_shares"],
            "成交筆數": None,
            "成交金額": row["turnover"],
            "漲跌(+/-)": row["sign"],
            "漲跌價差": row["change_value"],
            "最後揭示買價": None,
            "最後揭示買量": None,
            "最後揭示賣價": None,
            "最後揭示賣量": None,
            "本益比": None,
        }

    path.write_text(
        json.dumps(
            {
                "schema_version": "historical-price-spike-repair-test",
                "source_date": "20260520",
                "plan_hash": "sha256:test-plan",
                "allowlist_hash": "sha256:test-allowlist",
                "canonical_sha256": "sha256:test-canonical",
                "db_path": str(db_path.resolve()),
                "allowlist_count": len(canonical),
                "apply_allowed": False,
                "source_update_columns": ["收盤價"],
                "rows": [
                    {
                        "symbol": symbol,
                        "date": "20260520",
                        "source": raw_source(row),
                    }
                    for symbol, row in canonical.items()
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _apply_fixture_price_state(
    db_path: Path, canonical: dict[str, dict[str, object]]
) -> None:
    """Model the already-applied price receipt before technical apply."""
    with sqlite3.connect(db_path) as connection:
        for row in canonical.values():
            connection.execute(
                'UPDATE daily_prices SET "開盤價" = ?, "最高價" = ?, '
                '"最低價" = ?, "收盤價" = ?, "成交股數" = ? '
                'WHERE "證券代號" = ? AND "日期" = ?',
                (
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row["volume_shares"],
                    row["symbol"],
                    row["date"],
                ),
            )
        connection.commit()


def _write_fixture_price_receipt(
    path: Path,
    db_path: Path,
    price_plan: dict[str, object],
    backup_path: Path,
) -> None:
    body: dict[str, object] = {
        "schema_version": "historical-price-spike-repair-test",
        "receipt_kind": "historical_price_spike_repair",
        "status": "applied",
        "source_date": "20260520",
        "plan_hash": price_plan["plan_hash"],
        "allowlist_hash": price_plan["allowlist_hash"],
        "db_path": str(db_path.resolve()),
        "backup_path": str(backup_path.resolve()),
        "backup_sha256": apply_guard._sha256_file(backup_path),
        "rows": price_plan["rows"],
    }
    final = dict(body)
    final["receipt_sha256"] = apply_guard._price_payload_hash(body)
    path.write_text(json.dumps(final, ensure_ascii=False), encoding="utf-8")
    path.with_name("pending.json").write_text(
        json.dumps({"status": "applied_receipt_written"}, ensure_ascii=False),
        encoding="utf-8",
    )


def _write_fixture_caches(
    data_root: Path,
    symbols: list[str],
    dates: list[str],
) -> None:
    header = ["日期", "證券代號", *DEPENDENT_INDICATORS]
    technical_dir = data_root / "technical_analysis"
    meta_dir = data_root / "meta_data"
    technical_dir.mkdir(parents=True)
    meta_dir.mkdir(parents=True)
    rows: list[list[object]] = []
    for symbol in symbols:
        symbol_rows = []
        for key in dates[dates.index("20260520") :]:
            values = [key, symbol, *([999.0] * len(DEPENDENT_INDICATORS))]
            symbol_rows.append(values)
            rows.append(values)
        (technical_dir / f"{symbol}_indicators.csv").write_text(
            "\n".join(
                [
                    ",".join(header),
                    *[",".join(str(value) for value in row) for row in symbol_rows],
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    (meta_dir / "all_stocks_data.csv").write_text(
        "\n".join(
            [
                ",".join(header),
                *[",".join(str(value) for value in row) for row in rows],
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_apply_writer_uses_independent_cache_old_values_and_row_bound_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "data"
    db_path = data_root / "sqlite" / "twstock.db"
    db_path.parent.mkdir(parents=True)
    dates, canonical = _make_fixture_db(db_path)
    _apply_fixture_price_state(db_path, canonical)
    price_plan_path = tmp_path / "price_plan.json"
    _write_fixture_price_plan(price_plan_path, db_path, canonical)
    price_plan = json.loads(price_plan_path.read_text(encoding="utf-8"))
    price_backup = tmp_path / "price_backup.db"
    shutil.copy2(db_path, price_backup)
    price_receipt = tmp_path / "price_receipt.json"
    _write_fixture_price_receipt(price_receipt, db_path, price_plan, price_backup)
    _write_fixture_caches(data_root, ["1001", "2002"], dates)
    manifest_path = tmp_path / "dryrun.json"
    run_dryrun(
        db_path=db_path,
        overlay_path=price_plan_path,
        output_path=manifest_path,
        data_root=data_root,
        symbols=["1001", "2002"],
    )

    technical_backup_hash_calls: list[Path] = []
    original_sha256_file = apply_guard._sha256_file

    def counted_sha256_file(path: Path) -> str:
        resolved = Path(path).resolve()
        if resolved.name == "technical_sqlite_before_repair.db":
            technical_backup_hash_calls.append(resolved)
        return original_sha256_file(path)

    monkeypatch.setattr(apply_guard, "_sha256_file", counted_sha256_file)
    receipt_dir = tmp_path / "technical_receipt"
    result = apply_guard.apply_technical_plan(
        dryrun_manifest_path=manifest_path,
        price_plan_path=price_plan_path,
        price_receipt_path=price_receipt,
        data_root=data_root,
        receipt_dir=receipt_dir,
        lock_path=tmp_path / "release" / ".ml_heavy_chain.lock",
        confirm=apply_guard.CONFIRM_TOKEN,
    )

    assert result["status"] == "applied"
    assert result["row_bound_rollback"] is True
    assert result["cache_files"]
    cache_journals = [Path(item["journal_path"]) for item in result["cache_files"]]
    assert all(path.is_file() for path in cache_journals)
    # Cache input deliberately used 999 rather than DB old cells.  The
    # journal proves cache old/new custody is independent from DB old/new.
    journal = json.loads(cache_journals[0].read_text(encoding="utf-8"))
    assert any(str(item["old"]) == "999.0" for item in journal["operations"])
    # The 3.6 GB formal backup is hashed once when it becomes durable and
    # once for the final receipt; cache progress must reuse that value rather
    # than rescanning it for every published cache file.
    assert len(technical_backup_hash_calls) == 2

    rollback = apply_guard.rollback_technical_receipt(
        receipt_path=receipt_dir / "receipt.json",
        lock_path=tmp_path / "release" / ".ml_heavy_chain.lock",
        confirm=apply_guard.CONFIRM_TOKEN,
    )
    assert rollback["status"] == "rolled_back"
    assert rollback["cache_rollback_required"] is False


def test_apply_writer_rejects_db_cell_drift_and_keeps_backup(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    db_path = data_root / "sqlite" / "twstock.db"
    db_path.parent.mkdir(parents=True)
    dates, canonical = _make_fixture_db(db_path)
    _apply_fixture_price_state(db_path, canonical)
    price_plan_path = tmp_path / "price_plan.json"
    _write_fixture_price_plan(price_plan_path, db_path, canonical)
    price_plan = json.loads(price_plan_path.read_text(encoding="utf-8"))
    price_backup = tmp_path / "price_backup.db"
    shutil.copy2(db_path, price_backup)
    price_receipt = tmp_path / "price_receipt.json"
    _write_fixture_price_receipt(price_receipt, db_path, price_plan, price_backup)
    _write_fixture_caches(data_root, ["1001", "2002"], dates)
    manifest_path = tmp_path / "dryrun.json"
    run_dryrun(
        db_path=db_path,
        overlay_path=price_plan_path,
        output_path=manifest_path,
        data_root=data_root,
        symbols=["1001", "2002"],
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            'UPDATE technical_indicators SET "SMA30" = ? WHERE "證券代號" = ? AND "日期" = ?',
            (12345.0, "1001", "20260520"),
        )
        connection.commit()
    receipt_dir = tmp_path / "technical_receipt"
    with pytest.raises(ApplyGuardError, match="technical old drift|technical old"):
        apply_guard.apply_technical_plan(
            dryrun_manifest_path=manifest_path,
            price_plan_path=price_plan_path,
            price_receipt_path=price_receipt,
            data_root=data_root,
            receipt_dir=receipt_dir,
            lock_path=tmp_path / "release" / ".ml_heavy_chain.lock",
            confirm=apply_guard.CONFIRM_TOKEN,
        )
    assert (receipt_dir / "technical_sqlite_before_repair.db").is_file()
    pending = json.loads((receipt_dir / "pending.json").read_text(encoding="utf-8"))
    assert pending["status"] in {"failed_before_commit", "cache_rolled_back_before_db_commit"}


def test_cache_stage_skips_missing_rows_and_matches_blank_as_null(tmp_path: Path) -> None:
    cache_path = tmp_path / "1001_indicators.csv"
    cache_path.write_text(
        "日期,證券代號,SMA30\n20260520,1001,\n",
        encoding="utf-8",
    )
    staging_dir = tmp_path / "staging"
    result = apply_guard._stage_cache_file(
        path=cache_path,
        operations=[
            {
                "symbol": "1001",
                "date": "20260520",
                "column": "SMA30",
                "column_ordinal": 0,
                "new": 2.0,
                "cache_expected_old": None,
            },
            {
                "symbol": "1001",
                "date": "20260521",
                "column": "SMA30",
                "column_ordinal": 0,
                "new": 3.0,
            },
        ],
        staging_dir=staging_dir,
        label="missing-row",
    )

    assert result["status"] == "staged_with_missing_rows"
    assert result["changed_cells"] == 1
    assert result["missing_cell_count"] == 1
    staged = Path(result["staging_path"])
    assert "20260521" not in staged.read_text(encoding="utf-8")
    assert ",2.0\n" in staged.read_text(encoding="utf-8")
