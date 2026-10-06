"""Current quarterly statement candidate is bounded, Decimal and PIT explicit."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3

import pytest

from scripts.apply_current_statement_snapshot import apply_candidate, review_candidate
from scripts.build_current_statement_snapshot_candidate import build_candidate


def test_builder_handles_mixed_tpex_identity_without_guessing_units_or_basis(tmp_path: Path) -> None:
    openapi = tmp_path / "openapi"
    openapi.mkdir()
    income = [
        {
            "出表日期": "1150909",
            "年度": "115",
            "季別": "2",
            "公司代號": "1101",
            "公司名稱": "台泥",
            "營業收入": "1,234.00",
            "基本每股盈餘（元）": "0.38",
        }
    ]
    balance = [
        {
            "Date": "1150908",
            "年度": "115",
            "季別": "2",
            "SecuritiesCompanyCode": "1240",
            "CompanyName": "茂生農經",
            "資產總計": "99.00",
        }
    ]
    _write_json(openapi / "twse_income.json", income)
    _write_json(openapi / "tpex_balance.json", balance)
    manifest = {
        "schema_version": "official-openapi-statement-endpoints.v1",
        "captured_at": "2026-09-08T10:00:00+00:00",
        "endpoints": {
            "twse_income.json": _endpoint(openapi / "twse_income.json", "twse", "income"),
            "tpex_balance.json": _endpoint(openapi / "tpex_balance.json", "tpex", "balance"),
        },
    }
    _write_json(openapi / "endpoint_manifest.json", manifest)
    availability = tmp_path / "availability"
    availability.mkdir()
    _write_mapping(
        availability / "mapping.csv",
        [
            ("1101", "income_statement"),
            ("1240", "balance_sheet"),
        ],
    )

    output = tmp_path / "candidate"
    result = build_candidate(
        openapi_root=openapi,
        availability_roots=(availability,),
        output_root=output,
        period="2026-Q2",
        observed_at=datetime(2026, 9, 8, 10, tzinfo=timezone.utc),
    )

    assert result["coverage"]["current_stock_count"] == 2
    assert result["coverage"]["current_identity_missing_announcement_evidence_count"] == 0
    assert result["source_policy"]["formal_pit_eligible"] is False
    with (output / "statement_current_observations.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    income_rows = [row for row in rows if row["stock_code"] == "1101"]
    assert income_rows
    assert all(row["item_code"].startswith("income_statement:") for row in income_rows)
    assert all("損益表:期間基礎未驗證:" in row["item_name"] for row in income_rows)
    assert all(row["period_basis"] == "unknown" for row in income_rows)
    assert all(row["basis_verified"] == "0" for row in income_rows)
    assert all(row["aggregate_feature_eligible"] == "0" for row in income_rows)
    assert next(row for row in income_rows if "每股" in row["item_name"])["unit"] == "unknown"
    assert next(row for row in income_rows if "營業收入" in row["item_name"])["value"] == "1234.00"
    balance_row = next(row for row in rows if row["stock_code"] == "1240")
    assert balance_row["item_code"].startswith("balance_sheet:")
    assert balance_row["item_name"].startswith("資產負債表:期間基礎未驗證:")
    assert balance_row["unit"] == "unknown"


def test_builder_accepts_cashflow_endpoint_without_guessing_ytd_basis(tmp_path: Path) -> None:
    openapi = tmp_path / "openapi"
    openapi.mkdir()
    cashflow = [
        {
            "出表日期": "1150909",
            "年度": "115",
            "季別": "2",
            "公司代號": "2330",
            "營業活動之淨現金流入（流出）": "-12.5",
        }
    ]
    _write_json(openapi / "cashflow.json", cashflow)
    manifest = {
        "schema_version": "official-openapi-statement-endpoints.v1",
        "captured_at": "2026-09-08T10:00:00+00:00",
        "endpoints": {
            "cashflow.json": _endpoint(openapi / "cashflow.json", "twse", "cashflow"),
        },
    }
    _write_json(openapi / "endpoint_manifest.json", manifest)
    availability = tmp_path / "availability"
    availability.mkdir()
    _write_mapping(availability / "mapping.csv", [("2330", "cash_flows_statement")])

    result = build_candidate(
        openapi_root=openapi,
        availability_roots=(availability,),
        output_root=tmp_path / "candidate",
        period="2026-Q2",
        observed_at=datetime(2026, 9, 8, 10, tzinfo=timezone.utc),
    )

    rows = list(
        csv.DictReader(
            (tmp_path / "candidate" / "statement_current_observations.csv").open(
                encoding="utf-8-sig", newline=""
            )
        )
    )
    assert result["coverage"]["current_statement_type_counts"] == {
        "cash_flows_statement": 1
    }
    assert rows[0]["item_code"].startswith("cash_flows_statement:")
    assert rows[0]["item_name"].startswith("現金流量表:期間基礎未明示:")
    assert rows[0]["value"] == "-12.5"
    assert rows[0]["unit"] == "unknown"
    assert rows[0]["period_basis"] == "unknown"
    assert rows[0]["basis_verified"] == "0"
    assert rows[0]["aggregate_feature_eligible"] == "0"


def test_builder_quarantines_conflicting_duplicate_values(tmp_path: Path) -> None:
    openapi = tmp_path / "openapi"
    openapi.mkdir()
    first = [
        {"出表日期": "1150909", "年度": "115", "季別": "2", "公司代號": "1101", "營業收入": "1"}
    ]
    second = [
        {"出表日期": "1150909", "年度": "115", "季別": "2", "公司代號": "1101", "營業收入": "2", "營業成本": "3"}
    ]
    _write_json(openapi / "first.json", first)
    _write_json(openapi / "second.json", second)
    _write_json(
        openapi / "endpoint_manifest.json",
        {
            "captured_at": "2026-09-08T10:00:00+00:00",
            "endpoints": {
                "first.json": _endpoint(openapi / "first.json", "twse", "income"),
                "second.json": _endpoint(openapi / "second.json", "twse", "income"),
            },
        },
    )
    availability = tmp_path / "availability"
    availability.mkdir()
    _write_mapping(availability / "mapping.csv", [("1101", "income_statement")])

    result = build_candidate(
        openapi_root=openapi,
        availability_roots=(availability,),
        output_root=tmp_path / "candidate",
        period="2026-Q2",
        observed_at=datetime(2026, 9, 8, 10, tzinfo=timezone.utc),
    )
    assert result["diagnostics"]["conflicting_value_count"] == 1
    with (tmp_path / "candidate" / "statement_current_observations.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    assert not any(row["item_code"] == "income_statement:營業收入" for row in rows)
    assert any(row["item_code"] == "income_statement:營業成本" for row in rows)


def test_apply_review_and_sqlite_backup_are_safe(tmp_path: Path) -> None:
    openapi = tmp_path / "openapi"
    openapi.mkdir()
    source = [
        {"出表日期": "1150909", "年度": "115", "季別": "2", "公司代號": "1101", "營業收入": "1"}
    ]
    _write_json(openapi / "income.json", source)
    _write_json(
        openapi / "endpoint_manifest.json",
        {
            "captured_at": "2026-09-08T10:00:00+00:00",
            "endpoints": {"income.json": _endpoint(openapi / "income.json", "twse", "income")},
        },
    )
    availability = tmp_path / "availability"
    availability.mkdir()
    _write_mapping(availability / "mapping.csv", [("1101", "income_statement")])
    output = tmp_path / "candidate"
    build_candidate(
        openapi_root=openapi,
        availability_roots=(availability,),
        output_root=output,
        period="2026-Q2",
        observed_at=datetime(2026, 9, 8, 10, tzinfo=timezone.utc),
    )
    candidate = output / "statement_current_observations.csv"
    manifest = output / "statement_current_candidate.json"
    reviewed = review_candidate(candidate, manifest)
    assert reviewed["database_written"] is False

    database = tmp_path / "db.sqlite"
    sqlite3.connect(database).close()
    applied = apply_candidate(
        candidate=candidate,
        manifest=manifest,
        db_file=database,
        backup_dir=tmp_path / "backup",
    )
    assert applied["inserted_count"] == 1
    with sqlite3.connect(database) as connection:
        value = connection.execute(
            "SELECT value FROM fundamental_current_observations WHERE stock_code='1101'"
        ).fetchone()[0]
        assert value == "1"
    with sqlite3.connect(applied["backup"]) as backup:
        assert backup.execute("PRAGMA quick_check").fetchone()[0] == "ok"


def test_新版正規化保留舊列並可冪等重跑(tmp_path: Path) -> None:
    """原始端點不變時，新正規化列另存版本，舊猜測單位資料保持不動。"""
    openapi = tmp_path / "openapi"
    openapi.mkdir()
    endpoint_path = openapi / "income.json"
    _write_json(
        endpoint_path,
        [
            {
                "SecuritiesCompanyCode": "1101",
                "Year": "115",
                "Season": "2",
                "Revenue": "1,234.00",
            }
        ],
    )
    endpoint_sha256 = hashlib.sha256(endpoint_path.read_bytes()).hexdigest()
    raw_source_version = (
        "official-openapi-statement-endpoints.v1:sha256:" + endpoint_sha256
    )
    manifest = {
        "schema_version": "official-openapi-statement-endpoints.v1",
        "captured_at": "2026-09-08T10:00:00+00:00",
        "endpoints": {
            "income.json": _endpoint(endpoint_path, "twse", "income"),
        },
    }
    _write_json(openapi / "endpoint_manifest.json", manifest)
    availability = tmp_path / "availability"
    availability.mkdir()
    _write_mapping(availability / "mapping.csv", [("1101", "income_statement")])
    output = tmp_path / "candidate"
    build_candidate(
        openapi_root=openapi,
        availability_roots=(availability,),
        output_root=output,
        period="2026-Q2",
        observed_at=datetime(2026, 9, 8, 10, tzinfo=timezone.utc),
    )
    candidate = output / "statement_current_observations.csv"
    candidate_manifest = output / "statement_current_candidate.json"
    with candidate.open(encoding="utf-8-sig", newline="") as stream:
        new_row = next(
            row
            for row in csv.DictReader(stream)
            if row["item_code"] == "income_statement:Revenue"
        )
    assert new_row["source_version"].startswith(
        "official-openapi-current-statement-normalizer.v2:twse:income:2026-Q2:"
        f"raw:{raw_source_version}:derived:sha256:"
    )
    assert new_row["value"] == "1234.00"
    assert new_row["unit"] == "unknown"
    assert new_row["period_basis"] == "unknown"
    assert new_row["basis_verified"] == "0"
    assert new_row["aggregate_feature_eligible"] == "0"

    database = tmp_path / "current.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """CREATE TABLE fundamental_current_observations (
            stock_code TEXT NOT NULL, kind TEXT NOT NULL, period TEXT NOT NULL,
            as_of_date TEXT NOT NULL, item_code TEXT NOT NULL, item_name TEXT NOT NULL,
            value TEXT NOT NULL, unit TEXT NOT NULL, observed_at TEXT NOT NULL,
            source TEXT NOT NULL, source_version TEXT NOT NULL, market TEXT NOT NULL,
            PRIMARY KEY(stock_code, kind, period, item_code, source_version))"""
        )
        connection.execute(
            "INSERT INTO fundamental_current_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                new_row["stock_code"],
                new_row["kind"],
                new_row["period"],
                new_row["as_of_date"],
                new_row["item_code"],
                "損益表:YTD:Revenue",
                "1234000.00",
                "TWD",
                new_row["observed_at"],
                new_row["source"],
                raw_source_version,
                new_row["market"],
            ),
        )

    endpoint_bytes_before = endpoint_path.read_bytes()
    first = apply_candidate(
        candidate=candidate,
        manifest=candidate_manifest,
        db_file=database,
        backup_dir=tmp_path / "backup-first",
    )
    assert first["inserted_count"] == 1
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT source_version,item_name,value,unit,period_basis,basis_verified,"
            "aggregate_feature_eligible FROM fundamental_current_observations "
            "WHERE stock_code='1101' ORDER BY source_version"
        ).fetchall()
    old_row = next(row for row in rows if row[0] == raw_source_version)
    normalized_row = next(row for row in rows if row[0] == new_row["source_version"])
    assert old_row == (
        raw_source_version,
        "損益表:YTD:Revenue",
        "1234000.00",
        "TWD",
        "unknown",
        0,
        0,
    )
    assert normalized_row == (
        new_row["source_version"],
        new_row["item_name"],
        "1234.00",
        "unknown",
        "unknown",
        0,
        0,
    )
    assert len(rows) == 2
    assert endpoint_path.read_bytes() == endpoint_bytes_before
    assert hashlib.sha256(endpoint_bytes_before).hexdigest() == endpoint_sha256

    repeated = apply_candidate(
        candidate=candidate,
        manifest=candidate_manifest,
        db_file=database,
        backup_dir=tmp_path / "backup-repeat",
    )
    assert repeated["inserted_count"] == 0
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM fundamental_current_observations WHERE stock_code='1101'"
        ).fetchone()[0] == 2
        retained_old = connection.execute(
            "SELECT value,unit,source_version FROM fundamental_current_observations "
            "WHERE stock_code='1101' AND source_version=?",
            (raw_source_version,),
        ).fetchone()
    assert retained_old == ("1234000.00", "TWD", raw_source_version)


def test_輸出根與OpenAPI來源重疊時保留固定名稱端點原始bytes(tmp_path: Path) -> None:
    """固定候選檔名與端點重名時，必須在任何寫入前拒絕。"""
    openapi = tmp_path / "openapi"
    openapi.mkdir()
    endpoint_path = openapi / "statement_current_observations.csv"
    _write_json(
        endpoint_path,
        [
            {
                "SecuritiesCompanyCode": "1101",
                "Year": "115",
                "Season": "2",
                "Revenue": "1234",
            }
        ],
    )
    manifest_path = openapi / "endpoint_manifest.json"
    _write_json(
        manifest_path,
        {
            "schema_version": "official-openapi-statement-endpoints.v1",
            "captured_at": "2026-09-08T10:00:00+00:00",
            "endpoints": {
                endpoint_path.name: _endpoint(endpoint_path, "twse", "income")
            },
        },
    )
    availability = tmp_path / "availability"
    availability.mkdir()
    _write_mapping(availability / "mapping.csv", [("1101", "income_statement")])
    endpoint_before = endpoint_path.read_bytes()
    manifest_before = manifest_path.read_bytes()

    with pytest.raises(ValueError, match="來源根目錄重疊"):
        build_candidate(
            openapi_root=openapi,
            availability_roots=(availability,),
            output_root=openapi,
            period="2026-Q2",
            observed_at=datetime(2026, 9, 8, 10, tzinfo=timezone.utc),
        )

    assert endpoint_path.read_bytes() == endpoint_before
    assert manifest_path.read_bytes() == manifest_before
    assert not (openapi / "statement_availability_q2_mapping.csv").exists()
    assert not (openapi / "statement_current_candidate.json").exists()
    assert not (openapi / "statement_formal_pit_status.json").exists()
    assert not (openapi / "statement_current_preview.json").exists()
    assert not (openapi / "apply_current_statement_snapshot_command.txt").exists()


def test_輸出根與availability來源重疊時保留mapping原始bytes(tmp_path: Path) -> None:
    """候選輸出不得覆寫 availability mapping 或在來源目錄混入產物。"""
    openapi = tmp_path / "openapi"
    openapi.mkdir()
    endpoint_path = openapi / "income.json"
    _write_json(
        endpoint_path,
        [
            {
                "SecuritiesCompanyCode": "1101",
                "Year": "115",
                "Season": "2",
                "Revenue": "1234",
            }
        ],
    )
    _write_json(
        openapi / "endpoint_manifest.json",
        {
            "schema_version": "official-openapi-statement-endpoints.v1",
            "captured_at": "2026-09-08T10:00:00+00:00",
            "endpoints": {"income.json": _endpoint(endpoint_path, "twse", "income")},
        },
    )
    availability = tmp_path / "availability"
    availability.mkdir()
    mapping_path = availability / "mapping.csv"
    _write_mapping(mapping_path, [("1101", "income_statement")])
    mapping_before = mapping_path.read_bytes()

    with pytest.raises(ValueError, match="來源根目錄重疊"):
        build_candidate(
            openapi_root=openapi,
            availability_roots=(availability,),
            output_root=availability,
            period="2026-Q2",
            observed_at=datetime(2026, 9, 8, 10, tzinfo=timezone.utc),
        )

    assert mapping_path.read_bytes() == mapping_before
    assert not (availability / "statement_current_observations.csv").exists()
    assert not (availability / "statement_current_candidate.json").exists()


@pytest.mark.parametrize(
    ("source_kind", "output_name"),
    [
        ("endpoint", "statement_current_observations.csv"),
        ("manifest", "statement_current_candidate.json"),
        ("availability", "statement_availability_q2_mapping.csv"),
    ],
)
def test_輸出檔與任何來源硬連結相同時拒絕寫入(
    tmp_path: Path, source_kind: str, output_name: str
) -> None:
    """輸出別名若與端點、manifest 或 availability 共用實體檔，必須拒絕。"""
    openapi = tmp_path / "openapi"
    openapi.mkdir()
    endpoint_path = openapi / "income.json"
    _write_json(
        endpoint_path,
        [
            {
                "SecuritiesCompanyCode": "1101",
                "Year": "115",
                "Season": "2",
                "Revenue": "1234",
            }
        ],
    )
    _write_json(
        openapi / "endpoint_manifest.json",
        {
            "schema_version": "official-openapi-statement-endpoints.v1",
            "captured_at": "2026-09-08T10:00:00+00:00",
            "endpoints": {"income.json": _endpoint(endpoint_path, "twse", "income")},
        },
    )
    availability = tmp_path / "availability"
    availability.mkdir()
    mapping_path = availability / "mapping.csv"
    _write_mapping(mapping_path, [("1101", "income_statement")])
    output = tmp_path / "candidate"
    output.mkdir()
    output_path = output / output_name
    source_path = {
        "endpoint": endpoint_path,
        "manifest": openapi / "endpoint_manifest.json",
        "availability": mapping_path,
    }[source_kind]
    try:
        os.link(source_path, output_path)
    except OSError as exc:
        pytest.skip(f"此測試環境不支援建立硬連結：{type(exc).__name__}")
    source_before = source_path.read_bytes()

    with pytest.raises(ValueError, match="同一實體檔案"):
        build_candidate(
            openapi_root=openapi,
            availability_roots=(availability,),
            output_root=output,
            period="2026-Q2",
            observed_at=datetime(2026, 9, 8, 10, tzinfo=timezone.utc),
        )

    assert os.path.samefile(source_path, output_path)
    assert source_path.read_bytes() == source_before
    assert output_path.read_bytes() == source_before
    for other_output_name in (
        "statement_current_observations.csv",
        "statement_availability_q2_mapping.csv",
        "statement_current_candidate.json",
        "statement_formal_pit_status.json",
        "statement_current_preview.json",
        "apply_current_statement_snapshot_command.txt",
    ):
        other_output = output / other_output_name
        if other_output != output_path:
            assert not other_output.exists()


def test_觀測時鐘早於端點擷取時鐘時拒絕且不建立輸出(tmp_path: Path) -> None:
    """明確觀測時鐘不得回溯到原始端點擷取時間之前。"""
    openapi, availability, endpoint_path, manifest_path = _prepare_clock_test_sources(
        tmp_path, "2026-09-08T10:00:00+00:00"
    )
    endpoint_before = endpoint_path.read_bytes()
    manifest_before = manifest_path.read_bytes()
    mapping_path = availability / "mapping.csv"
    mapping_before = mapping_path.read_bytes()
    output = tmp_path / "candidate"

    with pytest.raises(ValueError, match="不得早於"):
        build_candidate(
            openapi_root=openapi,
            availability_roots=(availability,),
            output_root=output,
            period="2026-Q2",
            observed_at=datetime(2026, 9, 1, 10, tzinfo=timezone.utc),
        )

    assert not output.exists()
    assert endpoint_path.read_bytes() == endpoint_before
    assert manifest_path.read_bytes() == manifest_before
    assert mapping_path.read_bytes() == mapping_before


@pytest.mark.parametrize(
    "observed_at",
    [
        datetime(2026, 9, 8, 10, tzinfo=timezone.utc),
        datetime(2026, 9, 8, 10, 15, tzinfo=timezone.utc),
    ],
    ids=["與來源時鐘相同", "晚於來源時鐘"],
)
def test_觀測時鐘等於或晚於端點擷取時鐘可建置(
    tmp_path: Path, observed_at: datetime
) -> None:
    """相同或較晚的 aware 時鐘可用，輸出保留原 manifest 擷取時鐘。"""
    captured_at = "2026-09-08T10:00:00+00:00"
    openapi, availability, endpoint_path, manifest_path = _prepare_clock_test_sources(
        tmp_path, captured_at
    )
    manifest_before = manifest_path.read_bytes()
    endpoint_before = endpoint_path.read_bytes()
    output = tmp_path / "candidate"

    build_candidate(
        openapi_root=openapi,
        availability_roots=(availability,),
        output_root=output,
        period="2026-Q2",
        observed_at=observed_at,
    )

    with (output / "statement_current_observations.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    assert rows
    assert all(row["observed_at"] == observed_at.isoformat() for row in rows)
    candidate_manifest = json.loads(
        (output / "statement_current_candidate.json").read_text(encoding="utf-8")
    )
    assert candidate_manifest["source_snapshot"]["manifest_captured_at"] == captured_at
    assert manifest_path.read_bytes() == manifest_before
    assert endpoint_path.read_bytes() == endpoint_before


@pytest.mark.parametrize("captured_at", ["", "not-a-clock"], ids=["缺少擷取時鐘", "無效擷取時鐘"])
def test_來源擷取時鐘缺失或無效時拒絕且不建立輸出(
    tmp_path: Path, captured_at: str
) -> None:
    """來源時鐘未知時不得用呼叫端 override 猜補。"""
    openapi, availability, endpoint_path, manifest_path = _prepare_clock_test_sources(
        tmp_path, captured_at
    )
    endpoint_before = endpoint_path.read_bytes()
    manifest_before = manifest_path.read_bytes()
    output = tmp_path / "candidate"

    with pytest.raises(ValueError, match="captured_at must be ISO-8601"):
        build_candidate(
            openapi_root=openapi,
            availability_roots=(availability,),
            output_root=output,
            period="2026-Q2",
            observed_at=datetime(2026, 9, 8, 11, tzinfo=timezone.utc),
        )

    assert not output.exists()
    assert endpoint_path.read_bytes() == endpoint_before
    assert manifest_path.read_bytes() == manifest_before


def test_apply_review_rejects_future_observed_at(tmp_path: Path) -> None:
    openapi = tmp_path / "openapi"
    openapi.mkdir()
    source = [
        {"出表日期": "1150909", "年度": "115", "季別": "2", "公司代號": "1101", "營業收入": "1"}
    ]
    _write_json(openapi / "income.json", source)
    _write_json(
        openapi / "endpoint_manifest.json",
        {
            "captured_at": "2026-09-08T10:00:00+00:00",
            "endpoints": {"income.json": _endpoint(openapi / "income.json", "twse", "income")},
        },
    )
    availability = tmp_path / "availability"
    availability.mkdir()
    _write_mapping(availability / "mapping.csv", [("1101", "income_statement")])
    output = tmp_path / "candidate"
    build_candidate(
        openapi_root=openapi,
        availability_roots=(availability,),
        output_root=output,
        period="2026-Q2",
        observed_at=datetime(2026, 9, 8, 10, tzinfo=timezone.utc),
    )
    candidate = output / "statement_current_observations.csv"
    manifest = output / "statement_current_candidate.json"
    text = candidate.read_text(encoding="utf-8-sig").replace(
        "2026-09-08T10:00:00+00:00", "2099-01-01T00:00:00+00:00"
    )
    candidate.write_text(text, encoding="utf-8-sig", newline="")
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    manifest_payload["artifacts"]["observations_csv_sha256"] = (
        "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()
    )
    manifest.write_text(json.dumps(manifest_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="future observed_at"):
        review_candidate(candidate, manifest)


def _endpoint(path: Path, exchange: str, statement_type: str) -> dict[str, object]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "exchange": exchange,
        "statement_type": statement_type,
        "endpoint": "fixture",
        "url": f"https://example.invalid/{path.name}",
        "http_status": 200,
        "byte_count": path.stat().st_size,
        "sha256": digest,
        "row_count": 1,
        "status": "ok",
    }


def _prepare_clock_test_sources(
    tmp_path: Path, captured_at: str
) -> tuple[Path, Path, Path, Path]:
    """建立隔離的單筆官方端點與 availability 測試輸入。"""
    openapi = tmp_path / "openapi"
    openapi.mkdir()
    endpoint_path = openapi / "income.json"
    _write_json(
        endpoint_path,
        [
            {
                "SecuritiesCompanyCode": "1101",
                "Year": "115",
                "Season": "2",
                "Revenue": "1234",
            }
        ],
    )
    manifest_path = openapi / "endpoint_manifest.json"
    _write_json(
        manifest_path,
        {
            "schema_version": "official-openapi-statement-endpoints.v1",
            "captured_at": captured_at,
            "endpoints": {"income.json": _endpoint(endpoint_path, "twse", "income")},
        },
    )
    availability = tmp_path / "availability"
    availability.mkdir()
    _write_mapping(availability / "mapping.csv", [("1101", "income_statement")])
    return openapi, availability, endpoint_path, manifest_path


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_mapping(path: Path, identities: list[tuple[str, str]]) -> None:
    fieldnames = [
        "stock_code",
        "statement_type",
        "period",
        "as_of_date",
        "announced_date",
        "available_date",
        "source",
        "source_version",
        "availability_contract_version",
        "evidence_class",
        "source_hash",
        "revision",
        "parent_revision",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for stock_code, statement_type in identities:
            writer.writerow(
                {
                    "stock_code": stock_code,
                    "statement_type": statement_type,
                    "period": "2026-Q2",
                    "as_of_date": "2026-06-30",
                    "announced_date": "2026-08-12",
                    "available_date": "2026-08-13",
                    "source": "mops.ezsearch.statement_publication",
                    "source_version": "fixture",
                    "availability_contract_version": "formal-availability.v2",
                    "evidence_class": "official_announcement",
                    "source_hash": "sha256:" + "1" * 64,
                    "revision": "1",
                    "parent_revision": "",
                }
            )
