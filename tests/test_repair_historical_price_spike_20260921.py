from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
from typing import Any

import pytest


def _load_module():
    path = Path("scripts/repair_historical_price_spike_20260921.py")
    spec = importlib.util.spec_from_file_location("historical_price_repair", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FIELDS = [
    "證券代號",
    "證券名稱",
    "成交股數",
    "成交筆數",
    "成交金額",
    "開盤價",
    "最高價",
    "最低價",
    "收盤價",
    "漲跌(+/-)",
    "漲跌價差",
    "最後揭示買價",
    "最後揭示買量",
    "最後揭示賣價",
    "最後揭示賣量",
    "本益比",
]
SYMBOLS = ("1256", "1538", "2321", "5906")


def _source_rows() -> dict[str, dict[str, str]]:
    return {
        "1256": {
            "證券名稱": "鮮活果汁-KY", "成交股數": "111643", "成交筆數": "5717", "成交金額": "20663710",
            "開盤價": "185.00", "最高價": "189.00", "最低價": "183.00", "收盤價": "183.00",
            "漲跌(+/-)": "-", "漲跌價差": "0.50", "最後揭示買價": "183.00", "最後揭示買量": "1",
            "最後揭示賣價": "183.50", "最後揭示賣量": "2", "本益比": "13.82",
        },
        "1538": {
            "證券名稱": "正峰", "成交股數": "109", "成交筆數": "2", "成交金額": "1268",
            "開盤價": "", "最高價": "", "最低價": "", "收盤價": "", "漲跌(+/-)": "",
            "漲跌價差": "0.00", "最後揭示買價": "11.75", "最後揭示買量": "1",
            "最後揭示賣價": "12.40", "最後揭示賣量": "1", "本益比": "0.00",
        },
        "2321": {
            "證券名稱": "東訊", "成交股數": "414", "成交筆數": "5", "成交金額": "5259",
            "開盤價": "", "最高價": "", "最低價": "", "收盤價": "", "漲跌(+/-)": "",
            "漲跌價差": "0.00", "最後揭示買價": "12.70", "最後揭示買量": "1",
            "最後揭示賣價": "12.95", "最後揭示賣量": "1", "本益比": "0.00",
        },
        "5906": {
            "證券名稱": "台南-KY", "成交股數": "31", "成交筆數": "1", "成交金額": "1302",
            "開盤價": "", "最高價": "", "最低價": "", "收盤價": "", "漲跌(+/-)": "",
            "漲跌價差": "0.00", "最後揭示買價": "45.50", "最後揭示買量": "1",
            "最後揭示賣價": "46.25", "最後揭示賣量": "2", "本益比": "63.19",
        },
    }


def _old_view(symbol: str) -> dict[str, str]:
    values = {
        "1256": ("139", "139", "138.5", "139", "13001", "1806642", "0.5"),
        "1538": ("4.98", "4.98", "4.92", "4.97", "40353", "199638", "0.02"),
        "2321": ("12.1", "12.2", "11.9", "12.0", "1000", "12000", "0.1"),
        "5906": ("44", "45", "43.5", "44", "100", "4400", "0.2"),
    }[symbol]
    return {
        "date": "20260520", "symbol": symbol, "name": "old", "source": "sqlite", "market": "TWSE",
        "sign": "+", "open": values[0], "high": values[1], "low": values[2], "close": values[3],
        "volume_shares": values[4], "turnover": values[5], "change_value": values[6],
    }


def _canonical_view(module: Any, symbol: str, source: dict[str, str]) -> dict[str, Any]:
    return {
        "date": "20260520", "symbol": symbol, "name": source["證券名稱"], "source": "twse_raw",
        "market": "TWSE", "sign": module._normalise_sign(source["漲跌(+/-)"]),
        "open": module._decimal_text(source["開盤價"]), "high": module._decimal_text(source["最高價"]),
        "low": module._decimal_text(source["最低價"]), "close": module._decimal_text(source["收盤價"]),
        "volume_shares": source["成交股數"], "turnover": source["成交金額"],
        "change_value": module._decimal_text(source["漲跌價差"]),
        "sign_candidates": {"漲跌(+/-)": source["漲跌(+/-)"]},
    }


def _fixture(tmp_path: Path):
    module = _load_module()
    db = tmp_path / "twstock.db"
    canonical = tmp_path / "20260520.csv"
    audit = tmp_path / "audit.json"
    capture = tmp_path / "capture"
    capture.mkdir()
    receipt_dir = tmp_path / "receipts"
    lock = tmp_path / "maintenance.lock"
    source = _source_rows()

    columns_sql = ",\n".join(
        [
            '"日期" TEXT NOT NULL', '"證券代號" TEXT NOT NULL', '"證券名稱" TEXT',
            '"成交股數" INTEGER', '"成交筆數" INTEGER', '"成交金額" INTEGER',
            '"開盤價" REAL', '"最高價" REAL', '"最低價" REAL', '"收盤價" REAL',
            '"漲跌(+/-)" TEXT', '"漲跌價差" REAL', '"最後揭示買價" REAL',
            '"最後揭示買量" INTEGER', '"最後揭示賣價" REAL', '"最後揭示賣量" INTEGER',
            '"本益比" REAL', '"漲跌" TEXT', '"涨跌" TEXT', '"SMA30" REAL', '"legacy" REAL',
            'PRIMARY KEY ("證券代號", "日期")',
        ]
    )
    with sqlite3.connect(db) as connection:
        connection.execute(f"CREATE TABLE daily_prices ({columns_sql})")
        connection.execute("CREATE TABLE other_table (id INTEGER PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO other_table VALUES (1, 'unchanged')")
        for symbol in SYMBOLS:
            old = _old_view(symbol)
            connection.execute(
                "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "20260520", symbol, old["name"], int(old["volume_shares"]), 11, int(old["turnover"]),
                    float(old["open"]), float(old["high"]), float(old["low"]), float(old["close"]),
                    "+", float(old["change_value"]), float(old["close"]), 4, float(old["close"]), 1, 10.0,
                    "+", None, 7.25, 99.0,
                ),
            )
        connection.commit()

    with canonical.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        for symbol in SYMBOLS:
            writer.writerow({"證券代號": symbol, **source[symbol]})

    official_rows = []
    for symbol in SYMBOLS:
        row = source[symbol]
        sign = row["漲跌(+/-)"]
        official_sign = f"<p style= color:green>{sign}</p>" if sign == "-" else ("<p> </p>" if not sign else f"<p style= color:red>{sign}</p>")
        official_rows.append([row["證券代號"] if "證券代號" in row else symbol, row["證券名稱"], row["成交股數"], row["成交筆數"], row["成交金額"], row["開盤價"] or "--", row["最高價"] or "--", row["最低價"] or "--", row["收盤價"] or "--", official_sign, row["漲跌價差"], row["最後揭示買價"], row["最後揭示買量"], row["最後揭示賣價"], row["最後揭示賣量"], row["本益比"]])
    payload = {"stat": "OK", "date": "20260520", "tables": [{"title": "115年05月20日 每日收盤行情(全部)", "fields": FIELDS, "data": official_rows}]}
    decoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    response_path = capture / "response.json.gz"
    with gzip.open(response_path, "wb") as stream:
        stream.write(decoded)
    wire_hash = f"sha256:{hashlib.sha256(response_path.read_bytes()).hexdigest()}"
    decoded_hash = f"sha256:{hashlib.sha256(decoded).hexdigest()}"
    (capture / "receipt.json").write_text(
        json.dumps({"capture_timing": {"response_completed_at_utc": "2026-09-07T19:24:00.737021+00:00"}, "response": {"wire_sha256": wire_hash, "decoded_sha256": decoded_hash}, "safety": {"historical_decision_time_available": False}}, ensure_ascii=False),
        encoding="utf-8",
    )

    mismatch_rows = []
    for symbol in SYMBOLS:
        mismatch_rows.append({"date": "20260520", "symbol": symbol, "market": "TWSE", "differing_fields": ["close"], "sqlite": _old_view(symbol), "canonical_daily_csv": _canonical_view(module, symbol, source[symbol])})
    audit_payload = {
        "comparisons": {"sqlite_vs_canonical_daily_csv": {"mismatch_rows": mismatch_rows, "by_date": {"20260520": {"mismatch": len(SYMBOLS), "matched": 0, "missing_in_left": 0, "missing_in_right": 54}}}},
        "source_files": {"canonical_daily_csv": {"files": [{"date": "20260520", "path": str(canonical), "sha256": f"sha256:{hashlib.sha256(canonical.read_bytes()).hexdigest()}"}]}},
    }
    audit.write_text(json.dumps(audit_payload, ensure_ascii=False), encoding="utf-8")
    return module, db, audit, canonical, capture, receipt_dir, lock, source


def test_plan_and_apply_updates_all_quote_fields_and_preserves_technical(tmp_path: Path) -> None:
    module, db, audit, canonical, capture, receipt_dir, lock, source = _fixture(tmp_path)
    # Decode hash is derived from the gzip payload for the isolated fixture.
    with gzip.open(capture / "response.json.gz", "rb") as stream:
        decoded_hash = f"sha256:{hashlib.sha256(stream.read()).hexdigest()}"
    plan = module.prepare_plan(
        db_path=db, audit_path=audit, canonical_path=canonical, capture_dir=capture, receipt_dir=receipt_dir,
        expected_allowlist_count=len(SYMBOLS), expected_canonical_sha256=module._sha256_file(canonical),
        expected_official_wire_sha256=module._sha256_file(capture / "response.json.gz"), expected_official_decoded_sha256=decoded_hash,
    )
    assert plan["allowlist_count"] == 4
    assert plan["missing_ohlc_symbols"] == ["1538", "2321", "5906"]
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    final = module.apply_plan(
        plan, backup_path=receipt_dir / "before.db", pending_path=receipt_dir / "pending.json", receipt_path=receipt_dir / "receipt.json", lock_path=lock,
        expected_allowlist_count=len(SYMBOLS), pinned_canonical_sha256=plan["canonical_sha256"], pinned_official_wire_sha256=plan["official"]["wire_sha256"], pinned_official_decoded_sha256=plan["official"]["decoded_sha256"],
    )
    assert final["status"] == "applied"
    assert final["available_at"] is None
    assert final["official_capture_at"].startswith("2026-09-07T")
    with sqlite3.connect(db) as connection:
        row = connection.execute('SELECT "收盤價", "開盤價", "漲跌(+/-)", "漲跌", "SMA30" FROM daily_prices WHERE "證券代號" = "1256"').fetchone()
        assert row == (183.0, 185.0, "-", "-", 7.25)
        missing = connection.execute('SELECT "開盤價", "最高價", "最低價", "收盤價", "漲跌(+/-)" FROM daily_prices WHERE "證券代號" = "1538"').fetchone()
        assert missing == (None, None, None, None, None)
        assert connection.execute("SELECT value FROM other_table WHERE id=1").fetchone()[0] == "unchanged"


def test_source_hash_change_is_refused(tmp_path: Path) -> None:
    module, db, audit, canonical, capture, receipt_dir, lock, _ = _fixture(tmp_path)
    with gzip.open(capture / "response.json.gz", "rb") as stream:
        decoded_hash = f"sha256:{hashlib.sha256(stream.read()).hexdigest()}"
    plan = module.prepare_plan(
        db_path=db, audit_path=audit, canonical_path=canonical, capture_dir=capture, receipt_dir=receipt_dir,
        expected_allowlist_count=len(SYMBOLS), expected_canonical_sha256=module._sha256_file(canonical),
        expected_official_wire_sha256=module._sha256_file(capture / "response.json.gz"), expected_official_decoded_sha256=decoded_hash,
    )
    canonical.write_text(canonical.read_text(encoding="utf-8-sig") + "\n", encoding="utf-8-sig")
    with pytest.raises(module.SourceEvidenceError):
        module.apply_plan(
            plan, backup_path=receipt_dir / "before.db", pending_path=receipt_dir / "pending.json", receipt_path=receipt_dir / "receipt.json", lock_path=lock,
            expected_allowlist_count=len(SYMBOLS), pinned_canonical_sha256=plan["canonical_sha256"], pinned_official_wire_sha256=plan["official"]["wire_sha256"], pinned_official_decoded_sha256=plan["official"]["decoded_sha256"],
        )


def test_row_drift_is_refused_before_transaction(tmp_path: Path) -> None:
    module, db, audit, canonical, capture, receipt_dir, lock, _ = _fixture(tmp_path)
    with gzip.open(capture / "response.json.gz", "rb") as stream:
        decoded_hash = f"sha256:{hashlib.sha256(stream.read()).hexdigest()}"
    plan = module.prepare_plan(
        db_path=db, audit_path=audit, canonical_path=canonical, capture_dir=capture, receipt_dir=receipt_dir,
        expected_allowlist_count=len(SYMBOLS), expected_canonical_sha256=module._sha256_file(canonical),
        expected_official_wire_sha256=module._sha256_file(capture / "response.json.gz"), expected_official_decoded_sha256=decoded_hash,
    )
    with sqlite3.connect(db) as connection:
        connection.execute('UPDATE daily_prices SET "收盤價" = 999 WHERE "證券代號" = "1256"')
        connection.commit()
    with pytest.raises(module.RowDriftError):
        module.apply_plan(
            plan, backup_path=receipt_dir / "before.db", pending_path=receipt_dir / "pending.json", receipt_path=receipt_dir / "receipt.json", lock_path=lock,
            expected_allowlist_count=len(SYMBOLS), pinned_canonical_sha256=plan["canonical_sha256"], pinned_official_wire_sha256=plan["official"]["wire_sha256"], pinned_official_decoded_sha256=plan["official"]["decoded_sha256"],
        )


def test_row_bound_rollback_preserves_later_unrelated_writes(tmp_path: Path) -> None:
    module, db, audit, canonical, capture, receipt_dir, lock, _ = _fixture(tmp_path)
    with gzip.open(capture / "response.json.gz", "rb") as stream:
        decoded_hash = f"sha256:{hashlib.sha256(stream.read()).hexdigest()}"
    plan = module.prepare_plan(
        db_path=db, audit_path=audit, canonical_path=canonical, capture_dir=capture, receipt_dir=receipt_dir,
        expected_allowlist_count=len(SYMBOLS), expected_canonical_sha256=module._sha256_file(canonical),
        expected_official_wire_sha256=module._sha256_file(capture / "response.json.gz"), expected_official_decoded_sha256=decoded_hash,
    )
    receipt_path = receipt_dir / "receipt.json"
    module.apply_plan(
        plan, backup_path=receipt_dir / "before.db", pending_path=receipt_dir / "pending.json", receipt_path=receipt_path, lock_path=lock,
        expected_allowlist_count=len(SYMBOLS), pinned_canonical_sha256=plan["canonical_sha256"], pinned_official_wire_sha256=plan["official"]["wire_sha256"], pinned_official_decoded_sha256=plan["official"]["decoded_sha256"],
    )
    with sqlite3.connect(db) as connection:
        connection.execute('UPDATE daily_prices SET "SMA30" = 777 WHERE "證券代號" = "1256"')
        connection.execute("INSERT INTO other_table VALUES (2, 'later')")
        connection.commit()
    rollback = module.rollback_receipt(receipt_path, lock_path=lock)
    assert rollback["row_bound"] is True
    assert rollback["preserved_later_unrelated_writes"] is True
    with sqlite3.connect(db) as connection:
        row = connection.execute('SELECT "收盤價", "漲跌(+/-)", "SMA30" FROM daily_prices WHERE "證券代號" = "1256"').fetchone()
        assert row == (139.0, "+", 777.0)
        assert connection.execute("SELECT value FROM other_table WHERE id=2").fetchone()[0] == "later"


def test_trigger_side_effect_rolls_back_the_whole_transaction(tmp_path: Path) -> None:
    module, db, audit, canonical, capture, receipt_dir, lock, _ = _fixture(tmp_path)
    with sqlite3.connect(db) as connection:
        connection.execute(
            "CREATE TRIGGER audit_fixture_trigger AFTER UPDATE ON daily_prices "
            "BEGIN UPDATE other_table SET value='triggered' WHERE id=1; END;"
        )
        connection.commit()
    with gzip.open(capture / "response.json.gz", "rb") as stream:
        decoded_hash = f"sha256:{hashlib.sha256(stream.read()).hexdigest()}"
    plan = module.prepare_plan(
        db_path=db, audit_path=audit, canonical_path=canonical, capture_dir=capture, receipt_dir=receipt_dir,
        expected_allowlist_count=len(SYMBOLS), expected_canonical_sha256=module._sha256_file(canonical),
        expected_official_wire_sha256=module._sha256_file(capture / "response.json.gz"), expected_official_decoded_sha256=decoded_hash,
    )
    with pytest.raises(module.RepairError, match="unexpected trigger"):
        module.apply_plan(
            plan, backup_path=receipt_dir / "before.db", pending_path=receipt_dir / "pending.json", receipt_path=receipt_dir / "receipt.json", lock_path=lock,
            expected_allowlist_count=len(SYMBOLS), pinned_canonical_sha256=plan["canonical_sha256"], pinned_official_wire_sha256=plan["official"]["wire_sha256"], pinned_official_decoded_sha256=plan["official"]["decoded_sha256"],
        )
    with sqlite3.connect(db) as connection:
        assert connection.execute('SELECT "收盤價" FROM daily_prices WHERE "證券代號" = "1256"').fetchone()[0] == 139.0
        assert connection.execute("SELECT value FROM other_table WHERE id=1").fetchone()[0] == "unchanged"
    assert json.loads((receipt_dir / "pending.json").read_text(encoding="utf-8"))["status"] == "rolled_back_before_commit"


def test_receipt_write_failure_leaves_pending_and_committed_rows_traceable(tmp_path: Path) -> None:
    module, db, audit, canonical, capture, receipt_dir, lock, _ = _fixture(tmp_path)
    with gzip.open(capture / "response.json.gz", "rb") as stream:
        decoded_hash = f"sha256:{hashlib.sha256(stream.read()).hexdigest()}"
    plan = module.prepare_plan(
        db_path=db, audit_path=audit, canonical_path=canonical, capture_dir=capture, receipt_dir=receipt_dir,
        expected_allowlist_count=len(SYMBOLS), expected_canonical_sha256=module._sha256_file(canonical),
        expected_official_wire_sha256=module._sha256_file(capture / "response.json.gz"), expected_official_decoded_sha256=decoded_hash,
    )
    receipt_path = receipt_dir / "receipt.json"
    receipt_path.mkdir(parents=True)
    with pytest.raises(module.ReceiptError, match="final receipt"):
        module.apply_plan(
            plan, backup_path=receipt_dir / "before.db", pending_path=receipt_dir / "pending.json", receipt_path=receipt_path, lock_path=lock,
            expected_allowlist_count=len(SYMBOLS), pinned_canonical_sha256=plan["canonical_sha256"], pinned_official_wire_sha256=plan["official"]["wire_sha256"], pinned_official_decoded_sha256=plan["official"]["decoded_sha256"],
        )
    pending = json.loads((receipt_dir / "pending.json").read_text(encoding="utf-8"))
    assert pending["status"] == "commit_receipt_write_failed"
    with sqlite3.connect(db) as connection:
        assert connection.execute('SELECT "收盤價" FROM daily_prices WHERE "證券代號" = "1256"').fetchone()[0] == 183.0
