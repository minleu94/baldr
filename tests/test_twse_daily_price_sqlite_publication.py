"""TWSE prospective row evidence 的合成端到端契約。"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
import subprocess

import pytest

from data_module.config import TWStockConfig
from data_module.data_loader import DataLoader
from app_module.update_service import UpdateService
from data_module.db_manager import DBManager
from scripts.scheduled.run_daily_data_update_quick import (
    _sync_daily_price_files_with_twse_evidence,
)
from data_module.twse_daily_price_publication import read_sqlite_daily_price_evidence


_FIELDS = [
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


def _payload(rows: list[list[str]]) -> dict[str, object]:
    return {"stat": "OK", "tables": [{"fields": _FIELDS, "data": rows}]}


class _Response:
    status_code = 200
    url = "https://example.invalid/exchangeReport/MI_INDEX"
    headers = {"Content-Type": "application/json"}

    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
        self.content = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")

    def json(self) -> dict[str, object]:
        return self._payload


class _Session:
    def __init__(self, payload: dict[str, object]) -> None:
        self.response = _Response(payload)

    def get(self, *_args, **_kwargs) -> _Response:
        return self.response


def _config(tmp_path: Path) -> TWStockConfig:
    return TWStockConfig(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        profile="test",
        use_sqlite=True,
    )


def _row(
    code: str,
    name: str,
    *,
    close: str = "505.00",
    volume: str = "1,000",
) -> list[str]:
    return [
        code,
        name,
        volume,
        "10",
        "500,000",
        "500.00",
        "510.00",
        "499.00",
        close,
        "<p style= color:red>+</p>",
        "5.00",
        close,
        "1",
        "506.00",
        "2",
        "20.00",
    ]


def _download_and_sync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    rows: list[list[str]],
) -> tuple[TWStockConfig, dict[str, object], UpdateService]:
    config = _config(tmp_path)
    session = _Session(_payload(rows))
    monkeypatch.setattr("data_module.data_loader.requests.Session", lambda: session)
    monkeypatch.setattr("data_module.data_loader.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("data_module.data_loader.random.uniform", lambda _a, _b: 0)

    loader = DataLoader(config)
    downloaded = loader.download_from_api("2026-07-02")
    assert downloaded is not None
    diagnostics = loader.last_daily_download_diagnostics
    service = UpdateService(config)
    result = _sync_daily_price_files_with_twse_evidence(
        service,
        steps=[
            {
                "name": "update_twse_daily_prices",
                "status": "passed",
                "result": {"success": True, "source_diagnostics": [diagnostics]},
            },
            {
                "name": "update_tpex_daily_prices",
                "status": "warning",
                "result": {"success": False, "failure_diagnostics": [{"phase": "requested"}]},
            },
        ],
        start_date="2026-07-02",
        end_date="2026-07-02",
    )
    return config, result, service


def _read_row(
    config: TWStockConfig,
    sync_result: dict[str, object],
    *,
    symbol: str,
):
    descriptor = sync_result.get("row_evidence")
    return read_sqlite_daily_price_evidence(
        output_root=config.output_root,
        data_root=config.data_root,
        database_path=config.db_file,
        descriptor=descriptor if isinstance(descriptor, dict) else None,
        source_date="2026-07-02",
        stock_code=symbol,
    )


def test_twse_response_projects_observed_rows_only_after_sqlite_readback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, result, _service = _download_and_sync(
        tmp_path,
        monkeypatch,
        rows=[_row("2330", "台積電"), _row("2317", "鴻海", close="210.00")],
    )

    assert result["success"] is True
    assert result["synced_records"] == 2
    evidence = result.get("row_evidence")
    assert isinstance(evidence, dict)
    assert evidence["status"] == "captured"

    attested = _read_row(config, result, symbol="2330")
    assert attested.status == "attested"
    assert attested.row is not None
    assert attested.row.source_date == "20260702"
    assert attested.row.stock_code == "2330"
    assert attested.row.source_published_at is None
    assert attested.row.first_observed_at is not None
    assert attested.row.written_at is not None
    assert attested.row.csv_sha256.startswith("sha256:")
    assert attested.row.raw_response_sha256.startswith("sha256:")
    assert attested.row.sqlite_projection_row_sha256.startswith("sha256:")

    descriptor = evidence
    publication = json.loads(
        (config.output_root / descriptor["relative_path"]).read_text(encoding="utf-8")
    )
    published_row = next(row for row in publication["rows"] if row["stock_code"] == "2330")
    columns = published_row["projection_columns"]
    with DBManager(config).connect() as connection:
        selected = ", ".join(f'"{column}"' for column in columns)
        typed = ", ".join(f'typeof("{column}")' for column in columns)
        sqlite_row = connection.execute(
            f"SELECT {selected}, {typed} FROM daily_prices WHERE 日期=? AND 證券代號=?",
            ("20260702", "2330"),
        ).fetchone()
    typed_values = []
    for index, column in enumerate(columns):
        value = sqlite_row[index]
        kind = sqlite_row[len(columns) + index]
        if kind == "null":
            encoded = ["null"]
        elif kind == "integer":
            encoded = ["integer", str(value)]
        elif kind == "real":
            encoded = ["real", value.hex()]
        elif kind == "text":
            encoded = ["text", value]
        else:
            raise AssertionError(f"unexpected SQLite storage class: {kind}")
        typed_values.append([column, kind, encoded])
    expected_sqlite_hash = "sha256:" + hashlib.sha256(
        json.dumps(
            {"columns": columns, "values": typed_values},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert published_row["sqlite_projection_row_sha256"] == expected_sqlite_hash

    not_observed = _read_row(config, result, symbol="9999")
    assert not_observed.status == "unknown"
    assert not_observed.reason_code == "key_not_observed"


def test_legacy_or_skipped_csv_sync_does_not_mint_new_evidence(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.daily_price_dir.mkdir(parents=True, exist_ok=True)
    (config.daily_price_dir / "20260702.csv").write_text(
        "證券代號,證券名稱,收盤價\n2330,台積電,505.0\n",
        encoding="utf-8-sig",
    )
    service = UpdateService(config)

    result = service.sync_source_to_sqlite(
        "daily_price_files", "2026-07-02", "2026-07-02"
    )

    assert result["success"] is True
    assert result.get("row_evidence", {}).get("status") == "unknown"
    assert result.get("row_evidence", {}).get("reason_code") == "producer_manifest_missing"
    assert _read_row(config, result, symbol="2330").status == "unknown"


def test_invalid_projection_manifest_never_mints_row_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    session = _Session(_payload([_row("2330", "台積電")]))
    monkeypatch.setattr("data_module.data_loader.requests.Session", lambda: session)
    monkeypatch.setattr("data_module.data_loader.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("data_module.data_loader.random.uniform", lambda _a, _b: 0)
    loader = DataLoader(config)
    assert loader.download_from_api("2026-07-02") is not None
    diagnostic = dict(loader.last_daily_download_diagnostics)
    manifest_descriptor = dict(diagnostic["row_projection_manifest"])
    manifest_descriptor["sha256"] = "sha256:" + ("0" * 64)
    diagnostic["row_projection_manifest"] = manifest_descriptor

    result = UpdateService(config).sync_source_to_sqlite(
        "daily_price_files",
        "2026-07-02",
        "2026-07-02",
        row_evidence_source_diagnostics=[diagnostic],
    )

    assert result["success"] is True
    assert result["row_evidence"]["status"] == "unknown"
    assert _read_row(config, result, symbol="2330").status == "unknown"


def test_csv_rewritten_after_download_cannot_be_bound_to_original_raw_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    session = _Session(_payload([_row("2330", "台積電", close="505.00")]))
    monkeypatch.setattr("data_module.data_loader.requests.Session", lambda: session)
    monkeypatch.setattr("data_module.data_loader.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("data_module.data_loader.random.uniform", lambda _a, _b: 0)

    from data_module import twse_daily_price_publication

    create_manifest = twse_daily_price_publication.create_download_projection_manifest

    def rewrite_csv_before_manifest(**kwargs):
        Path(kwargs["csv_path"]).write_text(
            "證券代號,證券名稱,成交股數,成交筆數,成交金額,開盤價,最高價,最低價,收盤價,漲跌(+/-),漲跌價差,最後揭示買價,最後揭示買量,最後揭示賣價,最後揭示賣量,本益比\n"
            "2330,台積電,1000,10,500000,500,510,499,600,+,5,505,1,506,2,20\n",
            encoding="utf-8-sig",
        )
        return create_manifest(**kwargs)

    monkeypatch.setattr(
        twse_daily_price_publication,
        "create_download_projection_manifest",
        rewrite_csv_before_manifest,
    )
    loader = DataLoader(config)

    downloaded = loader.download_from_api("2026-07-02")

    assert downloaded is not None
    assert str(downloaded.iloc[0]["收盤價"]) == "505.0"
    assert loader.last_daily_download_diagnostics["row_projection_manifest"]["status"] == "unknown"


def test_response_json_accessor_must_match_captured_raw_body_for_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    parsed_payload = _payload([_row("2330", "台積電", close="505.00")])
    wire_payload = _payload([_row("2330", "台積電", close="600.00")])

    class _DivergentResponse(_Response):
        content = json.dumps(
            wire_payload, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")

        def __init__(self) -> None:
            self._payload = parsed_payload

    class _DivergentSession:
        response = _DivergentResponse()

        def get(self, *_args, **_kwargs) -> _Response:
            return self.response

    monkeypatch.setattr(
        "data_module.data_loader.requests.Session", lambda: _DivergentSession()
    )
    monkeypatch.setattr("data_module.data_loader.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("data_module.data_loader.random.uniform", lambda _a, _b: 0)
    loader = DataLoader(config)

    downloaded = loader.download_from_api("2026-07-02")

    assert downloaded is not None
    assert str(downloaded.iloc[0]["收盤價"]) == "505.0"
    assert loader.last_daily_download_diagnostics["row_projection_manifest"]["status"] == "unknown"


@pytest.mark.parametrize("tpex_close", ["505.00", "499.00"])
def test_any_twse_tpex_same_key_collision_is_not_attested(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tpex_close: str,
) -> None:
    config = _config(tmp_path)
    session = _Session(_payload([_row("2330", "台積電", close="505.00")]))
    monkeypatch.setattr("data_module.data_loader.requests.Session", lambda: session)
    monkeypatch.setattr("data_module.data_loader.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("data_module.data_loader.random.uniform", lambda _a, _b: 0)
    loader = DataLoader(config)
    assert loader.download_from_api("2026-07-02") is not None
    diagnostics = loader.last_daily_download_diagnostics

    config.tpex_daily_price_dir.mkdir(parents=True, exist_ok=True)
    (config.tpex_daily_price_dir / "20260702.csv").write_text(
        "日期,證券代號,證券名稱,收盤價\n"
        f"20260702,2330,台積電,{tpex_close}\n",
        encoding="utf-8-sig",
    )
    result = UpdateService(config).sync_source_to_sqlite(
        "daily_price_files",
        "2026-07-02",
        "2026-07-02",
        row_evidence_source_diagnostics=[diagnostics],
    )

    assert result["success"] is True
    assert _read_row(config, result, symbol="2330").status == "unknown"
    with DBManager(config).connect() as connection:
        row = connection.execute(
            'SELECT "收盤價" FROM daily_prices WHERE "日期"=? AND "證券代號"=?',
            ("20260702", "2330"),
        ).fetchone()
    assert row is not None
    assert Decimal(str(row[0])) == Decimal(tpex_close)


def test_byte_identical_full_twse_tpex_csv_collision_is_not_attested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    session = _Session(_payload([_row("2330", "台積電")]))
    monkeypatch.setattr("data_module.data_loader.requests.Session", lambda: session)
    monkeypatch.setattr("data_module.data_loader.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("data_module.data_loader.random.uniform", lambda _a, _b: 0)
    loader = DataLoader(config)
    assert loader.download_from_api("2026-07-02") is not None
    diagnostics = loader.last_daily_download_diagnostics

    twse_csv = config.daily_price_dir / "20260702.csv"
    tpex_csv = config.tpex_daily_price_dir / "20260702.csv"
    tpex_csv.parent.mkdir(parents=True, exist_ok=True)
    tpex_csv.write_bytes(twse_csv.read_bytes())
    assert tpex_csv.read_bytes() == twse_csv.read_bytes()

    result = UpdateService(config).sync_source_to_sqlite(
        "daily_price_files",
        "2026-07-02",
        "2026-07-02",
        row_evidence_source_diagnostics=[diagnostics],
    )

    assert result["success"] is True
    assert result["synced_records"] == 2
    assert result.get("row_evidence", {}).get("status") == "unknown"
    assert result.get("row_evidence", {}).get("reason_code") == (
        "no_unambiguous_readback_rows"
    )
    assert _read_row(config, result, symbol="2330").status == "unknown"


def test_duplicate_twse_key_is_not_attested(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config, result, _service = _download_and_sync(
        tmp_path,
        monkeypatch,
        rows=[_row("2330", "台積電", close="505.00"), _row("2330", "台積電", close="506.00")],
    )

    assert result["success"] is True
    assert _read_row(config, result, symbol="2330").status == "unknown"


def test_publication_failure_keeps_sqlite_success_but_reader_returns_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    session = _Session(_payload([_row("2330", "台積電")]))
    monkeypatch.setattr("data_module.data_loader.requests.Session", lambda: session)
    monkeypatch.setattr("data_module.data_loader.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("data_module.data_loader.random.uniform", lambda _a, _b: 0)
    loader = DataLoader(config)
    assert loader.download_from_api("2026-07-02") is not None
    diagnostics = loader.last_daily_download_diagnostics
    service = UpdateService(config)
    monkeypatch.setattr(
        "data_module.twse_daily_price_publication.publish_sqlite_row_evidence",
        lambda **_kwargs: (_ for _ in ()).throw(OSError("synthetic sidecar failure")),
    )

    result = service.sync_source_to_sqlite(
        "daily_price_files",
        "2026-07-02",
        "2026-07-02",
        row_evidence_source_diagnostics=[diagnostics],
    )

    assert result["success"] is True
    assert result.get("row_evidence", {}).get("status") == "unknown"
    assert result.get("row_evidence", {}).get("reason_code") == "publication_failed"
    assert _read_row(config, result, symbol="2330").status == "unknown"
    with DBManager(config).connect() as connection:
        assert connection.execute(
            'SELECT COUNT(*) FROM daily_prices WHERE "日期"=? AND "證券代號"=?',
            ("20260702", "2330"),
        ).fetchone()[0] == 1


def test_post_publication_sqlite_drift_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config, result, _service = _download_and_sync(
        tmp_path, monkeypatch, rows=[_row("2330", "台積電")]
    )
    with DBManager(config).connect() as connection:
        connection.execute(
            'UPDATE daily_prices SET "收盤價"=? WHERE "日期"=? AND "證券代號"=?',
            ("600.00", "20260702", "2330"),
        )

    readback = _read_row(config, result, symbol="2330")
    assert readback.status == "unknown"
    assert readback.reason_code == "sqlite_row_drift"


def test_partial_upsert_keeps_unobserved_old_key_but_never_attests_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    db = DBManager(config)
    with db.connect() as connection:
        connection.execute(
            'INSERT INTO daily_prices ("日期", "證券代號", "證券名稱", "收盤價") VALUES (?, ?, ?, ?)',
            ("20260702", "9999", "舊列", "100.00"),
        )

    session = _Session(_payload([_row("2330", "台積電")]))
    monkeypatch.setattr("data_module.data_loader.requests.Session", lambda: session)
    monkeypatch.setattr("data_module.data_loader.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("data_module.data_loader.random.uniform", lambda _a, _b: 0)
    loader = DataLoader(config)
    assert loader.download_from_api("2026-07-02") is not None
    result = _sync_daily_price_files_with_twse_evidence(
        UpdateService(config),
        steps=[
            {
                "name": "update_twse_daily_prices",
                "status": "passed",
                "result": {
                    "success": True,
                    "source_diagnostics": [loader.last_daily_download_diagnostics],
                },
            }
        ],
        start_date="2026-07-02",
        end_date="2026-07-02",
    )

    with db.connect() as connection:
        stale = connection.execute(
            'SELECT "收盤價" FROM daily_prices WHERE "日期"=? AND "證券代號"=?',
            ("20260702", "9999"),
        ).fetchone()
    assert stale is not None
    assert Decimal(str(stale[0])) == Decimal("100.00")
    assert _read_row(config, result, symbol="9999").status == "unknown"


def test_csv_overwrite_then_legacy_skip_sync_does_not_reuse_old_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, original_result, service = _download_and_sync(
        tmp_path, monkeypatch, rows=[_row("2330", "台積電")]
    )
    csv_path = config.daily_price_dir / "20260702.csv"
    csv_path.write_text(
        "證券代號,證券名稱,收盤價\n2330,台積電,600.00\n",
        encoding="utf-8-sig",
    )

    skipped_sync = service.sync_source_to_sqlite(
        "daily_price_files", "2026-07-02", "2026-07-02"
    )

    assert skipped_sync["success"] is True
    assert skipped_sync["row_evidence"]["reason_code"] == "producer_manifest_missing"
    assert _read_row(config, original_result, symbol="2330").status == "unknown"


def test_csv_overwrite_invalidates_manifest_when_current_diagnostic_is_supplied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    session = _Session(_payload([_row("2330", "台積電", close="505.00")]))
    monkeypatch.setattr("data_module.data_loader.requests.Session", lambda: session)
    monkeypatch.setattr("data_module.data_loader.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("data_module.data_loader.random.uniform", lambda _a, _b: 0)
    loader = DataLoader(config)
    assert loader.download_from_api("2026-07-02") is not None
    diagnostic = loader.last_daily_download_diagnostics
    csv_path = config.daily_price_dir / "20260702.csv"
    csv_path.write_text(
        "證券代號,證券名稱,收盤價\n2330,台積電,600.00\n",
        encoding="utf-8-sig",
    )

    result = UpdateService(config).sync_source_to_sqlite(
        "daily_price_files",
        "2026-07-02",
        "2026-07-02",
        row_evidence_source_diagnostics=[diagnostic],
    )

    assert result["success"] is True
    assert result["row_evidence"]["status"] == "unknown"
    assert _read_row(config, result, symbol="2330").status == "unknown"


def test_csv_overwrite_invalidates_current_projection_before_sync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    session = _Session(_payload([_row("2330", "台積電")] ))
    monkeypatch.setattr("data_module.data_loader.requests.Session", lambda: session)
    monkeypatch.setattr("data_module.data_loader.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("data_module.data_loader.random.uniform", lambda _a, _b: 0)
    loader = DataLoader(config)
    assert loader.download_from_api("2026-07-02") is not None

    csv_path = config.daily_price_dir / "20260702.csv"
    csv_path.write_text(
        "證券代號,證券名稱,收盤價\n2330,台積電,600.00\n",
        encoding="utf-8-sig",
    )
    result = _sync_daily_price_files_with_twse_evidence(
        UpdateService(config),
        steps=[
            {
                "name": "update_twse_daily_prices",
                "status": "passed",
                "result": {
                    "success": True,
                    "source_diagnostics": [loader.last_daily_download_diagnostics],
                },
            }
        ],
        start_date="2026-07-02",
        end_date="2026-07-02",
    )

    assert result["success"] is True
    assert result["row_evidence"]["status"] == "unknown"
    assert _read_row(config, result, symbol="2330").status == "unknown"


def test_explicit_no_data_never_creates_empty_or_negative_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    session = _Session({"stat": "很抱歉，沒有符合條件的資料!"})
    monkeypatch.setattr("data_module.data_loader.requests.Session", lambda: session)
    monkeypatch.setattr("data_module.data_loader.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("data_module.data_loader.random.uniform", lambda _a, _b: 0)
    loader = DataLoader(config)

    assert loader.download_from_api("2026-07-02") is None
    assert loader.last_daily_download_outcome == "no_data"
    result = _sync_daily_price_files_with_twse_evidence(
        UpdateService(config),
        steps=[
            {
                "name": "update_twse_daily_prices",
                "status": "passed",
                "result": {
                    "success": True,
                    "no_data_skipped_dates": ["2026-07-02"],
                    "source_diagnostics": [loader.last_daily_download_diagnostics],
                },
            },
            {
                "name": "update_tpex_daily_prices",
                "status": "warning",
                "result": {"success": False},
            },
        ],
        start_date="2026-07-02",
        end_date="2026-07-02",
    )

    assert result["success"] is True
    assert result["row_evidence"]["status"] == "unknown"
    assert result["row_evidence"]["reason_code"] == "no_rows_to_read_back"
    assert not (config.daily_price_dir / "20260702.csv").exists()


def test_scheduled_skip_handoff_does_not_discover_old_manifest_from_disk(
    tmp_path: Path,
) -> None:
    class _CaptureService:
        def __init__(self) -> None:
            self.kwargs: dict[str, object] = {}

        def sync_source_to_sqlite(self, *args, **kwargs):
            self.kwargs = kwargs
            return {"success": True}

    service = _CaptureService()
    result = _sync_daily_price_files_with_twse_evidence(
        service,
        steps=[
            {
                "name": "update_twse_daily_prices",
                "status": "passed",
                "result": {
                    "success": True,
                    "updated_dates": ["2026-07-02"],
                    "skipped_dates": ["2026-07-02"],
                    "source_diagnostics": [],
                },
            }
        ],
        start_date="2026-07-02",
        end_date="2026-07-02",
    )

    assert result["success"] is True
    assert service.kwargs["row_evidence_source_diagnostics"] == []


def test_update_daily_result_handoff_captures_current_manifest_but_skip_does_not(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    session = _Session(_payload([_row("2330", "台積電")]))
    monkeypatch.setattr("data_module.data_loader.requests.Session", lambda: session)
    monkeypatch.setattr("data_module.data_loader.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("data_module.data_loader.random.uniform", lambda _a, _b: 0)
    loader = DataLoader(config)
    assert loader.download_from_api("2026-07-02") is not None
    diagnostic = loader.last_daily_download_diagnostics
    csv_path = config.daily_price_dir / "20260702.csv"
    original_csv = csv_path.read_bytes()
    csv_path.unlink()

    service = UpdateService(config)
    monkeypatch.setattr(service, "_iter_weekday_date_keys", lambda *_args: ["20260702"])

    def run_batch(command: list[str], *, stdout, **_kwargs):
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_path.write_bytes(original_csv)
        stdout.write("2026-07-02 更新成功\n")
        stdout.write("UPDATE_DIAGNOSTIC " + json.dumps(diagnostic, ensure_ascii=True) + "\n")
        stdout.write("[UPDATE_SUMMARY] SUCCESS: 1 days, SKIPPED_NO_DATA: 0 days, FAILED: 0 days\n")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", run_batch)
    update_result = service.update_daily(
        "2026-07-02", "2026-07-02", delay_seconds=0
    )
    assert update_result["source_diagnostics"] == [diagnostic]
    synced = _sync_daily_price_files_with_twse_evidence(
        service,
        steps=[{"name": "update_twse_daily_prices", "result": update_result}],
        start_date="2026-07-02",
        end_date="2026-07-02",
    )
    assert _read_row(config, synced, symbol="2330").status == "attested"

    # 同一 CSV 後續被 update_daily 略過時沒有本次 descriptor，不可重用舊檔證據。
    skipped_service = UpdateService(config)
    monkeypatch.setattr(
        skipped_service, "_iter_weekday_date_keys", lambda *_args: ["20260702"]
    )
    skipped_result = skipped_service.update_daily(
        "2026-07-02", "2026-07-02", delay_seconds=0
    )
    assert skipped_result["updated_dates"] == []
    assert "source_diagnostics" not in skipped_result
    skipped_sync = _sync_daily_price_files_with_twse_evidence(
        skipped_service,
        steps=[{"name": "update_twse_daily_prices", "result": skipped_result}],
        start_date="2026-07-02",
        end_date="2026-07-02",
    )
    assert skipped_sync["row_evidence"]["status"] == "unknown"
    assert _read_row(config, skipped_sync, symbol="2330").status == "unknown"
