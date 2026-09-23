from __future__ import annotations

from datetime import date, datetime, timedelta
import gzip
import json
from pathlib import Path
import sqlite3

import pytest

import data_module.ml_restatement_current_capture as capture_module
from data_module.ml_restatement_current_capture import (
    _MARKET_COLUMNS,
    _PRICE_COLUMNS,
    capture_restated_current_dataset,
)
from data_module.ml_restatement_current_inputs import prepare_restated_current_inputs
from data_module.ml_restatement_research_dataset import sha256_file
from tests.test_ml_restatement_current_inputs import _fixture_dataset


class _Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        value = datetime.fromisoformat("2026-09-23T13:00:00+08:00")
        return value.astimezone(tz) if tz is not None else value.replace(tzinfo=None)


def _sources(root: Path) -> tuple[Path, Path]:
    db = root / "prices.sqlite"
    connection = sqlite3.connect(db)
    try:
        for table, columns in (("daily_prices", _PRICE_COLUMNS), ("market_indices", _MARKET_COLUMNS)):
            connection.execute("CREATE TABLE " + table + " (" + ",".join('"' + name + '" TEXT' for name in columns) + ")")
        repair_after = None
        for index in range(210):
            day = date(2026, 3, 1) + timedelta(days=index)
            market = {name: str(20_000 + index) for name in _MARKET_COLUMNS}
            market.update(日期=day.strftime("%Y%m%d"), 指數名稱="TAIEX")
            connection.execute("INSERT INTO market_indices VALUES (" + ",".join("?" for _ in _MARKET_COLUMNS) + ")", tuple(market[name] for name in _MARKET_COLUMNS))
            price = {name: str(100 + index) for name in _PRICE_COLUMNS}
            price.update(日期=day.strftime("%Y%m%d"), 證券代號="1256", 最高價=str(102 + index), 最低價=str(99 + index), 涨跌="+")
            connection.execute("INSERT INTO daily_prices VALUES (" + ",".join("?" for _ in _PRICE_COLUMNS) + ")", tuple(price[name] for name in _PRICE_COLUMNS))
            if day == date(2026, 5, 20):
                repair_after = price
        connection.commit()
    finally:
        connection.close()
    receipt = root / "repair.json"
    receipt.write_text(json.dumps({
        "schema_version": "historical-price-spike-repair-20260921.v1",
        "receipt_kind": "historical_price_spike_repair", "status": "applied",
        "available_at_backfilled": False, "historical_decision_time_available": False,
        "corrected_at": "2026-09-22T10:00:00+08:00", "source_date": "20260520",
        "allowlist_count": 1, "rows": [{"symbol": "1256", "after": repair_after}],
    }, ensure_ascii=False), encoding="utf-8")
    return db, receipt


def test_current_capture_freezes_t1_prefix_without_touching_source(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(capture_module, "datetime", _Clock)
    template, template_hash = _fixture_dataset(tmp_path / "template")
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    db, receipt = _sources(source_dir)
    before_hash = sha256_file(db)
    manifest, digest = capture_restated_current_dataset(
        database_path=db, template_manifest_path=template,
        expected_template_manifest_hash=template_hash,
        price_repair_receipt=receipt, expected_price_receipt_hash=sha256_file(receipt),
        symbols=("1256",), output_root=tmp_path / "captured",
    )
    assert sha256_file(db) == before_hash
    prepared = prepare_restated_current_inputs(
        manifest_path=manifest, expected_manifest_file_hash=digest,
        symbols=("1256",), captured_at=datetime.fromisoformat("2026-09-23T14:00:00+08:00"),
    )
    assert prepared.feature_asof_date == "2026-09-22"
    assert prepared.rows[0].targets is None
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["dataset_purpose"] == "current_inference_only"
    assert payload["verified_repair_symbols"] == ["1256"]
    with gzip.open(manifest.parent / "source_prefix.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            assert all(row["日期"] < "20260923" for row in json.loads(line)["rows"])


def test_current_capture_rejects_source_that_lost_the_price_repair(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(capture_module, "datetime", _Clock)
    template, template_hash = _fixture_dataset(tmp_path / "template")
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    db, receipt = _sources(source_dir)
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE daily_prices SET 收盤價='1' WHERE 日期='20260520'")
    with pytest.raises(ValueError, match="verified corrected prices"):
        capture_restated_current_dataset(
            database_path=db, template_manifest_path=template,
            expected_template_manifest_hash=template_hash,
            price_repair_receipt=receipt, expected_price_receipt_hash=sha256_file(receipt),
            symbols=("1256",), output_root=tmp_path / "captured",
        )
