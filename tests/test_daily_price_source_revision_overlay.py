from __future__ import annotations

import hashlib
import json
import logging
import shutil
import sys
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace

import pandas as pd
import pytest

from data_module.daily_price_source_revision_overlay import (
    DailyPriceSourceRevisionOverlayError,
)
from data_module.historical_session_revision import RECEIPT_DIR as SESSION_RECEIPT_DIR
from data_module.ml_daily_price_revision_gate import (
    REPAIR_RECEIPT_RELATIVE_DIR,
    REPAIR_SCHEMA,
)


PRICE_COLUMNS = [
    "證券名稱",
    "成交股數",
    "成交筆數",
    "成交金額",
    "開盤價",
    "最高價",
    "最低價",
    "收盤價",
    "漲跌(+/-)",
    "漲跌",
    "涨跌",
    "漲跌價差",
    "最後揭示買價",
    "最後揭示買量",
    "最後揭示賣價",
    "最後揭示賣量",
    "本益比",
]
OUTPUT_COLUMNS = ["日期", "證券代號", *PRICE_COLUMNS]


def _canonical_json_hash(payload: dict[str, object]) -> str:
    encoded = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _price_row(day: str, symbol: str, close: int) -> dict[str, object]:
    return {
        "日期": day,
        "證券代號": symbol,
        "證券名稱": f"測試股票{symbol}",
        "成交股數": 1000,
        "成交筆數": 10,
        "成交金額": close * 1000,
        "開盤價": close,
        "最高價": close + 2,
        "最低價": close - 2,
        "收盤價": close,
        "漲跌(+/-)": "+",
        "漲跌": "+",
        "涨跌": "+",
        "漲跌價差": 1,
        "最後揭示買價": close - 1,
        "最後揭示買量": 10,
        "最後揭示賣價": close,
        "最後揭示賣量": 10,
        "本益比": 0,
    }


def _write_applied_price_receipt(database_path: Path) -> Path:
    receipt_dir = (
        database_path.parent.parent / REPAIR_RECEIPT_RELATIVE_DIR
    )
    receipt_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for symbol, close in (("1256", 183), ("1477", 213)):
        after = _price_row("20260520", symbol, close)
        before = _price_row("20260520", symbol, close - 1)
        source = {**after, "date": "20260520", "symbol": symbol}
        rows.append(
            {
                "date": "20260520",
                "symbol": symbol,
                "before": before,
                "after": after,
                "source": source,
                "differing_fields": ["close", "open", "high", "low"],
            }
        )
    body: dict[str, object] = {
        "schema_version": REPAIR_SCHEMA,
        "receipt_kind": "historical_price_spike_repair",
        "status": "applied",
        "source_date": "20260520",
        "source_update_columns": PRICE_COLUMNS,
        "allowlist_count": len(rows),
        "allowlist_hash": "sha256:" + "a" * 64,
        "plan_hash": "sha256:" + "b" * 64,
        "canonical_sha256": "sha256:" + "c" * 64,
        "db_path": str(database_path.resolve()),
        "rows": rows,
    }
    receipt = {**body, "receipt_sha256": _canonical_json_hash(body)}
    receipt_path = receipt_dir / "receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    pending = {
        "schema_version": REPAIR_SCHEMA,
        "receipt_kind": "historical_price_spike_repair_pending",
        "status": "applied_receipt_written",
        "source_date": body["source_date"],
        "allowlist_count": body["allowlist_count"],
        "allowlist_hash": body["allowlist_hash"],
        "plan_hash": body["plan_hash"],
        "canonical_sha256": body["canonical_sha256"],
        "db_path": body["db_path"],
    }
    (receipt_dir / "pending.json").write_text(
        json.dumps(pending, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    return receipt_path


def _write_applied_session_plan(database_path: Path) -> Path:
    run_dir = (
        database_path.parent.parent / SESSION_RECEIPT_DIR / "run01"
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        _price_row("20141227", "1256", 103),
        _price_row("20141227", "5001", 20),
    ]
    for row in rows:
        row.pop("漲跌(+/-)")
        row["漲跌"] = "+"
    plan: dict[str, object] = {
        "schema_version": "historical-session-repair.v1",
        "database_path": str(database_path.resolve()),
        "dates": ["20141227"],
        "source_start_date": "2014-12-27",
        "source_end_date": "2014-12-27",
        "rows": rows,
    }
    plan_bytes = (
        json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    (run_dir / "plan.json").write_bytes(plan_bytes)
    plan_sha256 = hashlib.sha256(plan_bytes).hexdigest()
    receipt_bytes = (
        json.dumps(
            {
                "schema_version": "historical-session-repair.v1",
                "state": "applied",
                "plan_sha256": plan_sha256,
                "dates": plan["dates"],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    (run_dir / "receipt.json").write_bytes(receipt_bytes)
    marker = {
        "schema_version": "historical-session-revision.v1",
        "database_path": str(database_path.resolve()),
        "historical_pit": False,
        "plan_sha256": plan_sha256,
        "state": "applied",
        "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
    }
    marker_path = run_dir / "revision.json"
    marker_path.write_text(
        json.dumps(marker, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    return marker_path


def _setup(tmp_path: Path, *, include_raw: bool = True) -> SimpleNamespace:
    data_root = tmp_path / "FA_Data"
    meta_dir = data_root / "meta_data"
    daily_dir = data_root / "daily_price"
    tpex_dir = data_root / "daily_price_tpex"
    backup_dir = meta_dir / "backup"
    sqlite_dir = data_root / "sqlite"
    for directory in (meta_dir, daily_dir, tpex_dir, backup_dir, sqlite_dir):
        directory.mkdir(parents=True, exist_ok=True)
    database_path = sqlite_dir / "twstock.db"
    _write_applied_price_receipt(database_path)
    _write_applied_session_plan(database_path)

    output_file = meta_dir / "stock_data_whole.csv"
    existing_rows = [
        _price_row("20260520", "1256", 182),
        _price_row("20260520", "1477", 212),
        _price_row("20141227", "1256", 99),
        _price_row("20260714", "2330", 1000),
    ]
    pd.DataFrame(existing_rows, columns=OUTPUT_COLUMNS).to_csv(
        output_file, index=False, encoding="utf-8-sig"
    )
    if include_raw:
        pd.DataFrame(
            [
                _price_row("20260520", "1256", 182),
                _price_row("20260520", "1477", 212),
            ],
            columns=OUTPUT_COLUMNS,
        ).to_csv(daily_dir / "20260520.csv", index=False, encoding="utf-8-sig")
        pd.DataFrame(
            [_price_row("20141227", "1256", 99)], columns=OUTPUT_COLUMNS
        ).to_csv(daily_dir / "20141227.csv", index=False, encoding="utf-8-sig")

    return SimpleNamespace(
        profile="unit",
        data_root=data_root,
        data_dir=data_root,
        daily_price_dir=daily_dir,
        tpex_daily_price_dir=tpex_dir,
        meta_data_dir=meta_dir,
        backup_dir=backup_dir,
        stock_data_file=output_file,
        all_stocks_data_file=meta_dir / "all_stocks_data.csv",
        db_file=database_path,
    )


def _assert_canonical_output(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig", dtype={"日期": str, "證券代號": str})
    indexed = frame.set_index(["日期", "證券代號"])
    assert indexed.loc[("20260520", "1256"), "收盤價"] == 183
    assert indexed.loc[("20260520", "1477"), "收盤價"] == 213
    assert indexed.loc[("20141227", "1256"), "收盤價"] == 103
    assert indexed.loc[("20141227", "5001"), "收盤價"] == 20
    assert indexed.loc[("20260714", "2330"), "收盤價"] == 1000
    return frame


def test_main_merge_applies_verified_revisions_on_no_new_raw_and_keeps_raw(tmp_path: Path) -> None:
    from scripts.merge_daily_data import merge_daily_data

    config = _setup(tmp_path)
    raw_files = list(config.daily_price_dir.glob("*.csv"))
    raw_bytes = {path: path.read_bytes() for path in raw_files}

    result = merge_daily_data(force_all=False, config=config)

    assert result["success"] is True
    assert result.get("merged_files") == 0
    merged = _assert_canonical_output(config.stock_data_file)
    from data_module.daily_price_revision_write_guard import (
        prepare_daily_price_revision_frame,
    )

    prepared = prepare_daily_price_revision_frame(
        config.db_file,
        merged,
        replace_dates=["20141227", "20260520"],
    )
    pd.testing.assert_frame_equal(prepared, merged)
    assert {path: path.read_bytes() for path in raw_files} == raw_bytes


def test_main_merge_applies_verified_revisions_when_raw_directory_is_empty(tmp_path: Path) -> None:
    from scripts.merge_daily_data import merge_daily_data

    config = _setup(tmp_path, include_raw=False)

    result = merge_daily_data(force_all=False, config=config)

    assert result["success"] is True
    _assert_canonical_output(config.stock_data_file)


def test_main_merge_applies_revisions_when_raw_directories_are_missing(
    tmp_path: Path,
) -> None:
    from scripts.merge_daily_data import merge_daily_data

    config = _setup(tmp_path, include_raw=False)
    shutil.rmtree(config.daily_price_dir)
    shutil.rmtree(config.tpex_daily_price_dir)

    result = merge_daily_data(force_all=False, config=config)

    assert result["success"] is True
    _assert_canonical_output(config.stock_data_file)


def test_main_full_raw_remerge_applies_verified_revisions(tmp_path: Path) -> None:
    from scripts.merge_daily_data import merge_daily_data

    config = _setup(tmp_path)
    raw_files = list(config.daily_price_dir.glob("*.csv"))
    raw_bytes = {path: path.read_bytes() for path in raw_files}

    result = merge_daily_data(force_all=True, config=config)

    assert result["success"] is True
    frame = pd.read_csv(
        config.stock_data_file, encoding="utf-8-sig", dtype={"日期": str, "證券代號": str}
    ).set_index(["日期", "證券代號"])
    assert frame.loc[("20260520", "1256"), "收盤價"] == 183
    assert frame.loc[("20260520", "1477"), "收盤價"] == 213
    assert frame.loc[("20141227", "1256"), "收盤價"] == 103
    assert frame.loc[("20141227", "5001"), "收盤價"] == 20
    assert ("20260714", "2330") not in frame.index
    assert len(frame) == 4
    assert {path: path.read_bytes() for path in raw_files} == raw_bytes


def _install_exclusion_evidence(
    monkeypatch: pytest.MonkeyPatch,
    evidence: list[dict[str, object]],
) -> None:
    module = ModuleType("data_module.excluded_daily_price_revision")
    setattr(module, "load_exclusions", lambda database_path: set())
    setattr(module, "load_exclusion_evidence", lambda database_path: evidence)
    monkeypatch.setitem(sys.modules, module.__name__, module)


def test_merge_removes_only_verified_closed_dates_and_exact_exclusion_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.merge_daily_data import merge_daily_data

    config = _setup(tmp_path, include_raw=False)
    exclusion_evidence = [
        {
            "keys": [("20260520", "2330")],
            "closed_dates": ["20241002"],
            "plan_sha256": "b" * 64,
            "receipt_sha256": "c" * 64,
            "receipt_path": str(config.data_root / "excluded-receipt.json"),
        }
    ]
    _install_exclusion_evidence(monkeypatch, exclusion_evidence)
    existing = pd.read_csv(config.stock_data_file, encoding="utf-8-sig")
    extra_rows = pd.DataFrame(
        [
            _price_row("20241002", "0001", 10),
            _price_row("20241002", "9999", 20),
            _price_row("20260520", "2330", 30),
            _price_row("20260520", "9999", 40),
            _price_row("20241003", "0001", 50),
        ],
        columns=OUTPUT_COLUMNS,
    )
    pd.concat([existing, extra_rows], ignore_index=True).to_csv(
        config.stock_data_file, index=False, encoding="utf-8-sig"
    )

    result = merge_daily_data(force_all=False, config=config)

    assert result["success"] is True
    frame = pd.read_csv(
        config.stock_data_file, encoding="utf-8-sig", dtype={"日期": str, "證券代號": str}
    )
    keys = set(zip(frame["日期"], frame["證券代號"], strict=True))
    assert ("20241002", "0001") not in keys
    assert ("20241002", "9999") not in keys
    assert ("20260520", "2330") not in keys
    assert ("20260520", "9999") in keys
    assert ("20241003", "1") in keys
    receipt = json.loads(Path(result["source_receipt"]).read_text(encoding="utf-8"))
    assert receipt["excluded_source_rows_removed"] == 3
    exclusion_identity = next(
        item
        for item in receipt["source_revision_evidence"]
        if item["kind"] == "excluded_daily_price_revision"
    )
    assert exclusion_identity["receipt_sha256"] == "c" * 64


@pytest.mark.parametrize("corrupt_kind", ["price_receipt", "session_plan"])
def test_invalid_revision_evidence_stops_before_derived_publish(
    tmp_path: Path, corrupt_kind: str
) -> None:
    from scripts.merge_daily_data import merge_daily_data

    config = _setup(tmp_path)
    before_output = config.stock_data_file.read_bytes()
    raw_path = config.daily_price_dir / "20260520.csv"
    before_raw = raw_path.read_bytes()
    if corrupt_kind == "price_receipt":
        receipt_path = config.data_root / REPAIR_RECEIPT_RELATIVE_DIR / "receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["receipt_sha256"] = "sha256:" + "0" * 64
        receipt_path.write_text(
            json.dumps(receipt, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
    else:
        plan_path = (
            config.data_root / SESSION_RECEIPT_DIR / "run01" / "plan.json"
        )
        plan_path.write_bytes(plan_path.read_bytes() + b" ")

    with pytest.raises(DailyPriceSourceRevisionOverlayError, match="來源修訂證據缺漏"):
        merge_daily_data(force_all=False, config=config)

    assert config.stock_data_file.read_bytes() == before_output
    assert raw_path.read_bytes() == before_raw


def test_exclusion_identity_missing_hash_stops_before_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.merge_daily_data import merge_daily_data

    config = _setup(tmp_path, include_raw=False)
    before_output = config.stock_data_file.read_bytes()
    _install_exclusion_evidence(
        monkeypatch,
        [
            {
                "keys": [("20260520", "2330")],
                "closed_dates": [],
                "plan_sha256": "",
                "receipt_sha256": "d" * 64,
                "receipt_path": str(config.data_root / "excluded-receipt.json"),
            }
        ],
    )

    with pytest.raises(DailyPriceSourceRevisionOverlayError, match="來源修訂證據缺漏"):
        merge_daily_data(force_all=False, config=config)

    assert config.stock_data_file.read_bytes() == before_output


def test_legacy_loader_applies_verified_revisions_before_no_new_raw_return(
    tmp_path: Path,
) -> None:
    from data_module.data_loader import DataLoader

    config = _setup(tmp_path)
    config.all_stocks_data_file.write_bytes(config.stock_data_file.read_bytes())
    config.create_backup = lambda source, destination: shutil.copy2(source, destination)
    config.restore_backup = lambda source, destination: shutil.copy2(source, destination)
    loader = DataLoader.__new__(DataLoader)
    loader.config = config
    loader.logger = logging.getLogger("test-daily-price-source-revision-overlay")

    merged = loader.merge_daily_data()

    assert merged is not None
    _assert_canonical_output(config.all_stocks_data_file)
