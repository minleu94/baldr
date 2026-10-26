from __future__ import annotations

import gzip
import io
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

import data_module.twse_historical_daily_capture as capture_module
import scripts.capture_twse_historical_daily as capture_cli
from data_module.twse_historical_daily_capture import (
    TwseHistoricalCaptureError,
    capture_twse_historical_daily,
    load_twse_capture,
)


_DATE = "2026-05-20"
_SYMBOLS = ("3017", "1101")
_FIELDS = [
    "證券代號",
    "證券名稱",
    "開盤價",
    "最高價",
    "最低價",
    "收盤價",
    "成交股數",
]
_VALUES = {
    "3017": ("2425", "2435", "2325", "2340", "3568975"),
    "1101": ("33.1", "33.8", "32.8", "33.5", "1200000"),
}


def _official_payload() -> dict[str, object]:
    rows = [
        [symbol, f"name-{symbol}", *values[:3], values[3], values[4]]
        for symbol, values in _VALUES.items()
    ]
    return {
        "stat": "OK",
        "date": "20260520",
        "tables": [
            {
                "title": "個股日成交資訊",
                "fields": _FIELDS,
                "data": rows,
            }
        ],
    }


class _FakeResponse:
    status_code = 200
    url = (
        "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?"
        "date=20260520&type=ALL&response=json"
    )
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Content-Encoding": "gzip",
        "Date": "Sun, 07 Sep 2026 15:00:00 GMT",
        "ETag": "fixture-etag",
    }

    def __init__(self, payload: dict[str, object]) -> None:
        self.raw = io.BytesIO(
            gzip.compress(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8"),
                mtime=0,
            )
        )

    def close(self) -> None:
        self.raw.close()


class _FakeSession:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def get(self, *args: object, **kwargs: object) -> _FakeResponse:
        return _FakeResponse(self.payload)


def _build_sources(tmp_path: Path) -> tuple[Path, Path, Path]:
    sqlite_path = tmp_path / "sqlite" / "twstock.db"
    canonical_dir = tmp_path / "daily_price"
    backup_path = tmp_path / "backup" / "daily_price_20260520.csv"
    sqlite_path.parent.mkdir(parents=True)
    canonical_dir.mkdir(parents=True)
    backup_path.parent.mkdir(parents=True)
    header = "證券代號,證券名稱,開盤價,最高價,最低價,收盤價,成交股數\n"
    rows = "".join(
        f"{symbol},name-{symbol},{values[0]},{values[1]},{values[2]},"
        f"{values[3]},{values[4]}\n"
        for symbol, values in _VALUES.items()
    )
    (canonical_dir / "20260520.csv").write_text(
        header + rows,
        encoding="utf-8",
    )
    backup_path.write_text(header + rows, encoding="utf-8")
    with sqlite3.connect(sqlite_path) as connection:
        connection.execute(
            """
            CREATE TABLE daily_prices (
                日期 TEXT NOT NULL,
                證券代號 TEXT NOT NULL,
                證券名稱 TEXT,
                開盤價 TEXT,
                最高價 TEXT,
                最低價 TEXT,
                收盤價 TEXT,
                成交股數 INTEGER
            )
            """
        )
        connection.executemany(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ("20260520", "3017", "name-3017", "32.1", "32.4", "31.8", "31.9", 4105026),
                ("20260520", "1101", "name-1101", "33.1", "33.8", "32.8", "33.5", 1200000),
            ),
        )
    return sqlite_path, canonical_dir, backup_path


def test_capture_persists_official_wire_receipt_and_33_style_comparison(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sqlite_path, canonical_dir, backup_path = _build_sources(tmp_path)
    output = tmp_path / "repo-output"
    monkeypatch.setattr(
        capture_module.requests,
        "Session",
        lambda: _FakeSession(_official_payload()),
    )

    result = capture_twse_historical_daily(
        sqlite_path=sqlite_path,
        canonical_daily_price_dir=canonical_dir,
        date_value=_DATE,
        symbols=_SYMBOLS,
        historical_backup_path=backup_path,
        output_root=output,
    )

    assert result.capture_id == (
        f"twse-mi-index-{_DATE.replace('-', '')}-all-{result.response_sha256[7:23]}"
    )
    assert result.candidate_count == 1
    assert result.response_path.read_bytes()[:2] == b"\x1f\x8b"
    receipt, comparison = load_twse_capture(result.capture_directory)
    assert receipt["response"]["http_status"] == 200
    assert receipt["response"]["wire_bytes"] < receipt["response"]["decoded_bytes"]
    assert receipt["capture_timing"]["historical_decision_time_available"] is False
    assert comparison["verification"] == {
        "requested_symbol_count": 2,
        "official_row_count": 2,
        "official_requested_rows_present": True,
        "official_matches_sqlite_count": 1,
        "official_matches_current_canonical_count": 2,
        "official_matches_historical_backup_count": 2,
        "correction_candidate_count": 1,
    }
    row = next(row for row in comparison["rows"] if row["symbol"] == "3017")
    assert row["official_vs_sqlite_differing_fields"] == [
        "open",
        "high",
        "low",
        "close",
        "volume_shares",
    ]
    assert row["official_vs_current_canonical_differing_fields"] == []
    assert row["official_vs_historical_backup_differing_fields"] == []
    assert row["correction_status"] == "isolated_candidate_not_applied"

    # 同一 wire content 重跑只重用 immutable response/receipt/comparison。
    second = capture_twse_historical_daily(
        sqlite_path=sqlite_path,
        canonical_daily_price_dir=canonical_dir,
        date_value=_DATE,
        symbols=_SYMBOLS,
        historical_backup_path=backup_path,
        output_root=output,
    )
    assert second.capture_directory == result.capture_directory
    assert second.response_path.read_bytes() == result.response_path.read_bytes()
    assert second.receipt_path.read_bytes() == result.receipt_path.read_bytes()
    assert second.comparison_path.read_bytes() == result.comparison_path.read_bytes()


def test_capture_rejects_output_overlapping_read_only_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sqlite_path, canonical_dir, _ = _build_sources(tmp_path)
    monkeypatch.setattr(
        capture_module.requests,
        "Session",
        lambda: _FakeSession(_official_payload()),
    )
    with pytest.raises(TwseHistoricalCaptureError, match="outside"):
        capture_twse_historical_daily(
            sqlite_path=sqlite_path,
            canonical_daily_price_dir=canonical_dir,
            date_value=_DATE,
            symbols=_SYMBOLS,
            output_root=canonical_dir / "forbidden",
        )


def test_capture_rejects_official_response_missing_requested_symbol(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sqlite_path, canonical_dir, _ = _build_sources(tmp_path)
    payload = _official_payload()
    tables = payload["tables"]
    assert isinstance(tables, list)
    table = tables[0]
    assert isinstance(table, dict)
    table["data"] = table["data"][:1]
    monkeypatch.setattr(
        capture_module.requests,
        "Session",
        lambda: _FakeSession(payload),
    )
    with pytest.raises(TwseHistoricalCaptureError, match="misses requested"):
        capture_twse_historical_daily(
            sqlite_path=sqlite_path,
            canonical_daily_price_dir=canonical_dir,
            date_value=_DATE,
            symbols=_SYMBOLS,
            output_root=tmp_path / "repo-output",
        )


def test_capture_persists_official_no_data_as_non_price_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sqlite_path, canonical_dir, _ = _build_sources(tmp_path)
    output = tmp_path / "repo-output"
    monkeypatch.setattr(
        capture_module.requests,
        "Session",
        lambda: _FakeSession({"stat": "很抱歉，沒有符合條件的資料!"}),
    )

    result = capture_twse_historical_daily(
        sqlite_path=sqlite_path,
        canonical_daily_price_dir=canonical_dir,
        date_value=_DATE,
        symbols=_SYMBOLS,
        output_root=output,
    )

    receipt, comparison = load_twse_capture(result.capture_directory)
    assert result.status == "official_no_data_response"
    assert result.candidate_count == 0
    assert receipt["status"] == "official_no_data_response"
    assert receipt["official_payload"]["requested_symbols_present"] is False
    assert comparison["status"] == "official_no_data_response"
    assert comparison["verification"]["source_no_data"] is True
    assert comparison["verification"]["official_requested_rows_present"] is False
    assert comparison["verification"]["correction_candidate_count"] == 0
    assert comparison["rows"] == []
    assert result.response_path.read_bytes()[:2] == b"\x1f\x8b"
    assert not list(output.glob(".capture-*"))

    second = capture_twse_historical_daily(
        sqlite_path=sqlite_path,
        canonical_daily_price_dir=canonical_dir,
        date_value=_DATE,
        symbols=_SYMBOLS,
        output_root=output,
    )
    assert second.capture_directory == result.capture_directory
    assert second.receipt_path.read_bytes() == result.receipt_path.read_bytes()
    assert second.comparison_path.read_bytes() == result.comparison_path.read_bytes()

    different_scope = capture_twse_historical_daily(
        sqlite_path=sqlite_path,
        canonical_daily_price_dir=canonical_dir,
        date_value=_DATE,
        symbols=("3017",),
        output_root=output,
    )
    assert different_scope.response_sha256 == result.response_sha256
    assert different_scope.capture_directory != result.capture_directory
    _, different_comparison = load_twse_capture(different_scope.capture_directory)
    assert different_comparison["requested_symbols"] == ["3017"]


def test_capture_cleans_partial_temporary_response_when_download_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sqlite_path, canonical_dir, _ = _build_sources(tmp_path)
    output = tmp_path / "repo-output"

    def _fail_after_partial_write(**kwargs) -> None:
        response_path = kwargs["response_path"]
        response_path.write_bytes(b"partial-response")
        raise TwseHistoricalCaptureError("synthetic download failure")

    monkeypatch.setattr(capture_module, "_download_wire_response", _fail_after_partial_write)
    with pytest.raises(TwseHistoricalCaptureError, match="synthetic download failure"):
        capture_twse_historical_daily(
            sqlite_path=sqlite_path,
            canonical_daily_price_dir=canonical_dir,
            date_value=_DATE,
            symbols=_SYMBOLS,
            output_root=output,
        )

    assert not list(output.glob(".capture-*"))


def test_capture_cli_returns_dedicated_exit_code_for_official_no_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = SimpleNamespace(
        capture_id="capture-no-data",
        status="official_no_data_response",
        capture_directory=tmp_path / "capture",
        response_path=tmp_path / "capture" / "response.json.gz",
        receipt_path=tmp_path / "capture" / "receipt.json",
        comparison_path=tmp_path / "capture" / "comparison.json",
        response_sha256="sha256:" + "a" * 64,
        comparison_hash="sha256:" + "b" * 64,
        candidate_count=0,
    )
    monkeypatch.setattr(capture_cli, "capture_twse_historical_daily", lambda **_kwargs: result)

    exit_code = capture_cli.main(
        [
            "--sqlite",
            str(tmp_path / "source.sqlite"),
            "--daily-price-dir",
            str(tmp_path / "daily_price"),
            "--date",
            _DATE,
            "--symbol",
            "3017",
            "--output-root",
            str(tmp_path / "output"),
        ]
    )

    assert exit_code == 3
    assert json.loads(capsys.readouterr().out)["status"] == "official_no_data_response"
