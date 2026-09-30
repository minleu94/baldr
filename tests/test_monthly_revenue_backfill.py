from __future__ import annotations

import hashlib
import json
import sqlite3
import csv
from datetime import date

import pytest

import data_module.monthly_revenue_backfill as backfill_module
from data_module.fundamental_schema import apply_fundamental_schema
from data_module.monthly_revenue_backfill import (
    apply_mops_snapshot_monthly_revenue_backfill,
    apply_monthly_revenue_backfill,
    plan_mops_snapshot_monthly_revenue_backfill,
    plan_monthly_revenue_backfill,
)


def _write_revenue_csv(raw_dir, stock_code: str = "2330") -> None:
    raw_dir.mkdir()
    (raw_dir / f"{stock_code}_monthly_revenue.csv").write_text(
        "date,stock_id,country,revenue,revenue_month,revenue_year\n"
        f"2026-06-01,{stock_code},Taiwan,1000000000,5,2026\n",
        encoding="utf-8",
    )


def _write_availability_csv(path) -> None:
    path.write_text(
        "stock_code,period,as_of_date,announced_date,available_date,source,source_version,"
        "availability_contract_version,evidence_class,source_hash,revision,parent_revision\n"
        "2330,2026-05,2026-05-31,2026-06-10,2026-06-11,"
        "manual.twse_monthly_revenue_announcement_log,announcement-log-2026-06-16,"
        "formal-availability.v2,official_announcement,sha256:"
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,1,\n",
        encoding="utf-8",
    )


def _write_mops_snapshot_csv(path, *, fetched_at: str = "2026-06-10T08:00:00Z") -> None:
    path.write_text(
        "market,period,stock_code,company_name,current_month_revenue,"
        "previous_month_revenue,previous_year_month_revenue,mom_pct,yoy_pct,"
        "cumulative_revenue,previous_year_cumulative_revenue,cumulative_yoy_pct,"
        "note,fetched_at,source,source_version\n"
        "twse,2026-05,2330,台積電,320000000000,300000000000,250000000000,"
        "6.67,28.0,1500000000000,1200000000000,25.0,,"
        f"{fetched_at},mops.monthly_revenue_static_snapshot,"
        "mops-static-2026-06-16\n",
        encoding="utf-8-sig",
    )


def _scope_key_digest(keys: set[str]) -> str:
    return hashlib.sha256("\n".join(sorted(keys)).encode("utf-8")).hexdigest()


def _write_scope_manifest(
    path,
    *,
    candidate_file,
    accepted_file,
    accepted_keys: set[str],
    excluded_keys: list[str],
) -> None:
    candidate_bytes = candidate_file.read_bytes()
    accepted_bytes = accepted_file.read_bytes()
    candidate_key_set = accepted_keys | set(excluded_keys)
    path.write_text(
        json.dumps(
            {
                "candidate_file": str(candidate_file),
                "candidate_rows": len(candidate_key_set),
                "mapping_rows": len(accepted_keys),
                "accepted_rows": len(accepted_keys),
                "excluded_rows": len(excluded_keys),
                "excluded_keys": excluded_keys,
                "candidate_file_sha256": hashlib.sha256(candidate_bytes).hexdigest(),
                "accepted_file_sha256": hashlib.sha256(accepted_bytes).hexdigest(),
                "candidate_key_sha256": _scope_key_digest(candidate_key_set),
                "accepted_key_sha256": _scope_key_digest(accepted_keys),
                "excluded_key_sha256": _scope_key_digest(set(excluded_keys)),
            }
        ),
        encoding="utf-8",
    )


def _write_openapi_full_scope_fixture(tmp_path):
    from pathlib import Path

    root = tmp_path / "openapi-full-scope"
    source_dir = root / "source"
    source_dir.mkdir(parents=True)
    raw_rows = {
        "twse": [
            {
                "出表日期": "1150917",
                "資料年月": "11508",
                "公司代號": "2330",
                "公司名稱": "台積電",
                "產業別": "半導體業",
                "營業收入-當月營收": "1000",
                "營業收入-上月營收": "900",
                "營業收入-去年當月營收": "800",
                "營業收入-上月比較增減(%)": "11.111",
                "營業收入-去年同月增減(%)": "25.0",
                "累計營業收入-當月累計營收": "7000",
                "累計營業收入-去年累計營收": "6000",
                "累計營業收入-前期比較增減(%)": "16.666",
                "備註": "-",
            }
        ],
        "tpex": [
            {
                "出表日期": "1150917",
                "資料年月": "11508",
                "公司代號": "6488",
                "公司名稱": "環球晶",
                "產業別": "半導體業",
                "營業收入-當月營收": "2000",
                "營業收入-上月營收": "1900",
                "營業收入-去年當月營收": "1800",
                "營業收入-上月比較增減(%)": "5.263",
                "營業收入-去年同月增減(%)": "11.111",
                "累計營業收入-當月累計營收": "14000",
                "累計營業收入-去年累計營收": "13000",
                "累計營業收入-前期比較增減(%)": "7.692",
                "備註": "-",
            }
        ],
    }
    expected = {
        "twse": {
            "source": "twse.open_api.monthly_revenue",
            "source_id": "twse-openapi-t187ap05_L",
            "url": "https://openapi.twse.com.tw/v1/opendata/t187ap05_L",
            "captured_at": "2026-09-30T08:56:44.077872+00:00",
        },
        "tpex": {
            "source": "tpex.open_api.monthly_revenue",
            "source_id": "tpex-openapi-mopsfin_t187ap05_O",
            "url": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O",
            "captured_at": "2026-09-30T08:56:51.265713+00:00",
        },
    }
    raw_files: dict[str, bytes] = {}
    venue_versions: dict[str, str] = {}
    capture_results = {}
    for venue, rows in raw_rows.items():
        raw_bytes = json.dumps(
            rows, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        raw_files[venue] = raw_bytes
        raw_hash = hashlib.sha256(raw_bytes).hexdigest()
        venue_versions[venue] = (
            f"{expected[venue]['source_id']}-11508-sha256-{raw_hash}"
        )
        capture_results[venue] = {
            "requested_url": expected[venue]["url"],
            "status": "captured",
            "http_status": 200,
            "final_url": expected[venue]["url"],
            "observed_at_utc": expected[venue]["captured_at"],
            "content_sha256": raw_hash,
            "content_bytes": len(raw_bytes),
            "json_row_count": 1,
            "period_values_sample": ["11508"],
            "rows_for_2026_08": 1,
        }
        (source_dir / f"{venue}.json").write_bytes(raw_bytes)

    capture = {
        "schema_version": "monthly-revenue-openapi-capture.v1",
        "requested_period": "2026-08",
        "status": "captured",
        "results": capture_results,
    }
    capture_bytes = (json.dumps(capture, ensure_ascii=False, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    capture_path = source_dir / "capture_run.json"
    capture_path.write_bytes(capture_bytes)

    snapshot_columns = [
        "market", "period", "stock_code", "company_name", "current_month_revenue",
        "previous_month_revenue", "previous_year_month_revenue", "mom_pct", "yoy_pct",
        "cumulative_revenue", "previous_year_cumulative_revenue", "cumulative_yoy_pct",
        "note", "fetched_at", "source", "source_version",
    ]
    field_map = {
        "company_name": "公司名稱",
        "current_month_revenue": "營業收入-當月營收",
        "previous_month_revenue": "營業收入-上月營收",
        "previous_year_month_revenue": "營業收入-去年當月營收",
        "mom_pct": "營業收入-上月比較增減(%)",
        "yoy_pct": "營業收入-去年同月增減(%)",
        "cumulative_revenue": "累計營業收入-當月累計營收",
        "previous_year_cumulative_revenue": "累計營業收入-去年累計營收",
        "cumulative_yoy_pct": "累計營業收入-前期比較增減(%)",
        "note": "備註",
    }
    snapshot_rows = []
    for venue, rows in raw_rows.items():
        for raw_row in rows:
            row = {
                "market": venue,
                "period": "2026-08",
                "stock_code": raw_row["公司代號"],
                "fetched_at": expected[venue]["captured_at"],
                "source": expected[venue]["source"],
                "source_version": venue_versions[venue],
            }
            row.update({target: raw_row[source] for target, source in field_map.items()})
            snapshot_rows.append(row)
    snapshot_path = root / "snapshot.csv"
    with snapshot_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=snapshot_columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(snapshot_rows)

    availability_path = root / "availability.csv"
    availability_path.write_text(
        "stock_code,period,as_of_date,announced_date,available_date,source,source_version,"
        "availability_contract_version,evidence_class,source_hash,revision,parent_revision\n"
        "2330,2026-08,2026-08-31,2026-09-17,2026-10-01,"
        "twse.monthly_revenue_announcement,test-capture-version,formal-availability.v2,"
        "official_announcement,sha256:" + "a" * 64 + ",1,\n"
        "6488,2026-08,2026-08-31,2026-09-17,2026-10-01,"
        "twse.monthly_revenue_announcement,test-capture-version,formal-availability.v2,"
        "official_announcement,sha256:" + "b" * 64 + ",1,\n",
        encoding="utf-8",
    )

    key_set = {f"{row['stock_code']}|{row['period']}" for row in snapshot_rows}
    candidate_hash = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
    contract = {
        "schema_version": "monthly-revenue-source-contract.v1",
        "contract_id": "official_twse_tpex_openapi_monthly_revenue.v1",
        "composite_source": "twse_tpex.open_api.monthly_revenue_snapshot",
        "candidate_period": "2026-08",
        "candidate_available_at_utc": "2026-10-01T05:17:40.193719+00:00",
        "capture_manifest_file": "source/capture_run.json",
        "capture_manifest_sha256": hashlib.sha256(capture_bytes).hexdigest(),
        "venues": {
            venue: {
                "source": expected[venue]["source"],
                "source_id": expected[venue]["source_id"],
                "raw_file": f"source/{venue}.json",
                "raw_sha256": hashlib.sha256(raw_files[venue]).hexdigest(),
                "raw_bytes": len(raw_files[venue]),
                "row_count": 1,
                "captured_at_utc": expected[venue]["captured_at"],
                "source_version": venue_versions[venue],
            }
            for venue in ("twse", "tpex")
        },
    }
    manifest_path = root / "scope_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "monthly-revenue-full-official-research-scope.v1",
                "candidate_rows": 2,
                "mapping_rows": 2,
                "accepted_rows": 2,
                "excluded_rows": 0,
                "excluded_keys": [],
                "candidate_file": "snapshot.csv",
                "candidate_file_sha256": candidate_hash,
                "accepted_file_sha256": candidate_hash,
                "candidate_key_sha256": _scope_key_digest(key_set),
                "accepted_key_sha256": _scope_key_digest(key_set),
                "excluded_key_sha256": _scope_key_digest(set()),
                "source_scope": {
                    "period": "2026-08",
                    "twse_row_count": 1,
                    "tpex_row_count": 1,
                },
                "source_contract": contract,
                "owner_acceptance": False,
                "formal_apply_authorized": False,
                "historical_pit_credit": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return snapshot_path, availability_path, manifest_path, source_dir


def test_plan_monthly_revenue_backfill_requires_governed_mapping(tmp_path) -> None:
    raw_dir = tmp_path / "financial_data"
    _write_revenue_csv(raw_dir)
    availability_file = tmp_path / "missing_monthly_revenue_availability.csv"

    plan = plan_monthly_revenue_backfill(
        raw_dir=raw_dir,
        availability_file=availability_file,
        source_version="financial-data-csv-monthly-revenue-v1",
    )

    assert plan.records == ()
    assert plan.ready_for_apply is False
    assert plan.diagnostics[0].code == "fundamental_availability.mapping_file_missing"


def test_plan_monthly_revenue_backfill_builds_records_from_mapping(tmp_path) -> None:
    raw_dir = tmp_path / "financial_data"
    _write_revenue_csv(raw_dir)
    availability_file = tmp_path / "monthly_revenue_availability.csv"
    _write_availability_csv(availability_file)

    plan = plan_monthly_revenue_backfill(
        raw_dir=raw_dir,
        availability_file=availability_file,
        source_version="financial-data-csv-monthly-revenue-v1",
    )

    assert plan.ready_for_apply is True
    assert plan.raw_row_count == 1
    assert len(plan.records) == 1
    record = plan.records[0]
    assert record.stock_code == "2330"
    assert record.period == "2026-05"
    assert record.available_date == date(2026, 6, 11)
    assert record.source_version == "financial-data-csv-monthly-revenue-v1"
    assert plan.diagnostics == ()


def test_plan_mops_snapshot_monthly_revenue_backfill_preserves_mops_source(
    tmp_path,
) -> None:
    snapshot_file = tmp_path / "mops_snapshot.csv"
    _write_mops_snapshot_csv(snapshot_file)
    availability_file = tmp_path / "monthly_revenue_availability.csv"
    _write_availability_csv(availability_file)

    plan = plan_mops_snapshot_monthly_revenue_backfill(
        snapshot_file=snapshot_file,
        availability_file=availability_file,
        source_version="mops-static-snapshot-monthly-revenue-2026-06-16",
    )

    assert plan.ready_for_apply is True
    assert plan.raw_row_count == 1
    assert len(plan.records) == 1
    record = plan.records[0]
    assert record.stock_code == "2330"
    assert record.period == "2026-05"
    assert record.revenue == 320000000000
    assert record.source == "mops.monthly_revenue_static_snapshot"
    assert record.source_version == (
        "mops-static-snapshot-monthly-revenue-2026-06-16"
        "|snapshot=mops-static-2026-06-16"
    )
    assert plan.diagnostics == ()


def test_plan_openapi_full_scope_preserves_valid_twse_tpex_composite_source(
    tmp_path,
) -> None:
    snapshot_file, availability_file, scope_file, _ = _write_openapi_full_scope_fixture(
        tmp_path
    )

    plan = plan_mops_snapshot_monthly_revenue_backfill(
        snapshot_file=snapshot_file,
        availability_file=availability_file,
        source_version="monthly-revenue-openapi-research-2026-08",
        scope_manifest_file=scope_file,
    )

    assert plan.ready_for_apply is True
    assert plan.raw_row_count == 2
    assert len(plan.records) == 2
    assert {record.source for record in plan.records} == {
        "twse_tpex.open_api.monthly_revenue_snapshot"
    }
    assert {record.source_version for record in plan.records} == {
        "monthly-revenue-openapi-research-2026-08"
        "|snapshot=twse-openapi-t187ap05_L-11508-sha256-"
        + hashlib.sha256(
            (snapshot_file.parent / "source" / "twse.json").read_bytes()
        ).hexdigest(),
        "monthly-revenue-openapi-research-2026-08"
        "|snapshot=tpex-openapi-mopsfin_t187ap05_O-11508-sha256-"
        + hashlib.sha256(
            (snapshot_file.parent / "source" / "tpex.json").read_bytes()
        ).hexdigest(),
    }


def test_plan_snapshot_rejects_nonlegacy_sources_without_contract(tmp_path) -> None:
    snapshot_file, availability_file, _, _ = _write_openapi_full_scope_fixture(
        tmp_path
    )

    plan = plan_mops_snapshot_monthly_revenue_backfill(
        snapshot_file=snapshot_file,
        availability_file=availability_file,
        source_version="uncontracted-openapi-candidate",
    )

    assert plan.ready_for_apply is False
    assert any(
        diagnostic.code == "fundamental_revenue.snapshot_scope_manifest_invalid"
        for diagnostic in plan.diagnostics
    )


def test_plan_snapshot_rejects_unknown_source_without_contract(tmp_path) -> None:
    snapshot_file, availability_file, _, _ = _write_openapi_full_scope_fixture(
        tmp_path
    )
    with snapshot_file.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    rows[0]["source"] = "unregistered.monthly_revenue_source"
    with snapshot_file.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    plan = plan_mops_snapshot_monthly_revenue_backfill(
        snapshot_file=snapshot_file,
        availability_file=availability_file,
        source_version="uncontracted-unknown-source",
    )

    assert plan.ready_for_apply is False
    assert any(
        diagnostic.code == "fundamental_revenue.snapshot_scope_manifest_invalid"
        for diagnostic in plan.diagnostics
    )


def test_plan_snapshot_rejects_unknown_openapi_source_contract(tmp_path) -> None:
    snapshot_file, availability_file, scope_file, _ = _write_openapi_full_scope_fixture(
        tmp_path
    )
    manifest = json.loads(scope_file.read_text(encoding="utf-8"))
    manifest["source_contract"]["contract_id"] = "unknown-source-contract.v1"
    scope_file.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    plan = plan_mops_snapshot_monthly_revenue_backfill(
        snapshot_file=snapshot_file,
        availability_file=availability_file,
        source_version="monthly-revenue-openapi-research-2026-08",
        scope_manifest_file=scope_file,
    )

    assert plan.ready_for_apply is False
    assert any(
        diagnostic.code == "fundamental_revenue.snapshot_scope_manifest_invalid"
        for diagnostic in plan.diagnostics
    )


def test_plan_snapshot_rejects_scope_manifest_under_symlinked_root(tmp_path) -> None:
    snapshot_file, availability_file, scope_file, _ = _write_openapi_full_scope_fixture(
        tmp_path
    )
    linked_root = tmp_path / "linked-research-root"
    try:
        linked_root.symlink_to(scope_file.parent, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlinks are unavailable in this environment: {exc}")

    plan = plan_mops_snapshot_monthly_revenue_backfill(
        snapshot_file=snapshot_file,
        availability_file=availability_file,
        source_version="monthly-revenue-openapi-research-2026-08",
        scope_manifest_file=linked_root / scope_file.name,
    )

    assert plan.ready_for_apply is False
    assert any(
        diagnostic.code == "fundamental_revenue.snapshot_scope_manifest_invalid"
        for diagnostic in plan.diagnostics
    )


def test_source_contract_reader_rejects_oversized_file_before_read(tmp_path) -> None:
    large_file = tmp_path / "large_manifest.json"
    with large_file.open("wb") as handle:
        handle.write(b"x" * (backfill_module._MAX_SOURCE_CONTRACT_FILE_BYTES + 1))

    with pytest.raises(ValueError, match="bounded single-link regular file"):
        backfill_module._read_source_contract_file(tmp_path, large_file.name)


def test_source_contract_reader_rejects_file_growth_during_bounded_read(
    tmp_path, monkeypatch
) -> None:
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_bytes(b"{}")
    original_read = backfill_module.os.read
    appended = False

    def append_before_read(file_descriptor: int, byte_count: int) -> bytes:
        nonlocal appended
        if not appended:
            with manifest_file.open("ab") as handle:
                handle.write(b" ")
            appended = True
        return original_read(file_descriptor, byte_count)

    monkeypatch.setattr(backfill_module.os, "read", append_before_read)

    with pytest.raises(ValueError, match="changed while it was read"):
        backfill_module._read_source_contract_file(tmp_path, manifest_file.name)


def test_plan_snapshot_rejects_openapi_raw_bytes_outside_source_contract(tmp_path) -> None:
    snapshot_file, availability_file, scope_file, source_dir = (
        _write_openapi_full_scope_fixture(tmp_path)
    )
    raw_file = source_dir / "twse.json"
    raw_file.write_bytes(raw_file.read_bytes() + b" ")

    plan = plan_mops_snapshot_monthly_revenue_backfill(
        snapshot_file=snapshot_file,
        availability_file=availability_file,
        source_version="monthly-revenue-openapi-research-2026-08",
        scope_manifest_file=scope_file,
    )

    assert plan.ready_for_apply is False
    assert any(
        diagnostic.code == "fundamental_revenue.snapshot_scope_manifest_invalid"
        for diagnostic in plan.diagnostics
    )


def test_plan_snapshot_rejects_unapproved_mixed_source_with_valid_scope_hashes(
    tmp_path,
) -> None:
    snapshot_file, availability_file, scope_file, _ = _write_openapi_full_scope_fixture(
        tmp_path
    )
    with snapshot_file.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    rows[0]["source"] = "unregistered.monthly_revenue_source"
    with snapshot_file.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    manifest = json.loads(scope_file.read_text(encoding="utf-8"))
    snapshot_hash = hashlib.sha256(snapshot_file.read_bytes()).hexdigest()
    manifest["candidate_file_sha256"] = snapshot_hash
    manifest["accepted_file_sha256"] = snapshot_hash
    scope_file.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    plan = plan_mops_snapshot_monthly_revenue_backfill(
        snapshot_file=snapshot_file,
        availability_file=availability_file,
        source_version="monthly-revenue-openapi-research-2026-08",
        scope_manifest_file=scope_file,
    )

    assert plan.ready_for_apply is False
    assert any(
        diagnostic.code == "fundamental_revenue.snapshot_scope_manifest_invalid"
        for diagnostic in plan.diagnostics
    )


def test_plan_mops_snapshot_blocks_partial_mapping_and_keeps_full_denominator(tmp_path) -> None:
    snapshot_file = tmp_path / "mops_snapshot.csv"
    _write_mops_snapshot_csv(snapshot_file)
    with snapshot_file.open("a", encoding="utf-8") as handle:
        handle.write(
            "twse,2026-05,2317,鴻海,100,90,80,1.0,2.0,500,450,3.0,,"
            "2026-06-11T00:00:00Z,mops.monthly_revenue_static_snapshot,"
            "mops-static-twse-2026-05-sha256-"
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        )
    availability_file = tmp_path / "monthly_revenue_availability.csv"
    _write_availability_csv(availability_file)

    plan = plan_mops_snapshot_monthly_revenue_backfill(
        snapshot_file=snapshot_file,
        availability_file=availability_file,
        source_version="mops-static-snapshot-monthly-revenue-2026-06-16",
    )

    assert plan.raw_row_count == 2
    assert plan.snapshot_unmatched_mapping_count == 1
    assert len(plan.records) == 1
    assert plan.ready_for_apply is False
    assert any(
        diagnostic.code == "fundamental_availability.snapshot_mapping_incomplete"
        for diagnostic in plan.diagnostics
    )


def test_plan_mops_snapshot_accepts_explicit_partial_scope_manifest(tmp_path) -> None:
    snapshot_file = tmp_path / "accepted_scope.csv"
    _write_mops_snapshot_csv(snapshot_file)
    candidate_file = tmp_path / "full_candidate.csv"
    candidate_file.write_bytes(snapshot_file.read_bytes())
    with candidate_file.open("a", encoding="utf-8") as handle:
        handle.write(
            "twse,2026-05,2317,鴻海,100,90,80,1.0,2.0,500,450,3.0,,"
            "2026-06-11T00:00:00Z,mops.monthly_revenue_static_snapshot,"
            "mops-static-twse-2026-05-sha256-"
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        )
    availability_file = tmp_path / "monthly_revenue_availability.csv"
    _write_availability_csv(availability_file)
    manifest_file = tmp_path / "scope_manifest.json"
    _write_scope_manifest(
        manifest_file,
        candidate_file=candidate_file,
        accepted_file=snapshot_file,
        accepted_keys={"2330|2026-05"},
        excluded_keys=["2317|2026-05"],
    )

    plan = plan_mops_snapshot_monthly_revenue_backfill(
        snapshot_file=snapshot_file,
        availability_file=availability_file,
        source_version="mops-static-snapshot-monthly-revenue-2026-06-16",
        scope_manifest_file=manifest_file,
    )

    assert plan.ready_for_apply is True
    assert plan.snapshot_scope == "partial"
    assert plan.full_snapshot_row_count == 2
    assert plan.excluded_snapshot_row_count == 1
    assert plan.raw_row_count == 1
    assert len(plan.records) == 1
    assert plan.diagnostics == ()


def test_plan_mops_snapshot_rejects_scope_source_hash_or_key_drift(tmp_path) -> None:
    snapshot_file = tmp_path / "accepted_scope.csv"
    _write_mops_snapshot_csv(snapshot_file)
    candidate_file = tmp_path / "full_candidate.csv"
    candidate_file.write_bytes(snapshot_file.read_bytes())
    with candidate_file.open("a", encoding="utf-8") as handle:
        handle.write(
            "twse,2026-05,2317,鴻海,100,90,80,1.0,2.0,500,450,3.0,,"
            "2026-06-11T00:00:00Z,mops.monthly_revenue_static_snapshot,"
            "mops-static-twse-2026-05-sha256-"
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        )
    availability_file = tmp_path / "monthly_revenue_availability.csv"
    _write_availability_csv(availability_file)
    manifest_file = tmp_path / "scope_manifest.json"
    _write_scope_manifest(
        manifest_file,
        candidate_file=candidate_file,
        accepted_file=snapshot_file,
        accepted_keys={"2330|2026-05"},
        excluded_keys=["2317|2026-05"],
    )
    snapshot_file.write_text(
        snapshot_file.read_text(encoding="utf-8-sig")
        + "\n",
        encoding="utf-8-sig",
    )

    plan = plan_mops_snapshot_monthly_revenue_backfill(
        snapshot_file=snapshot_file,
        availability_file=availability_file,
        source_version="mops-static-snapshot-monthly-revenue-2026-06-16",
        scope_manifest_file=manifest_file,
    )

    assert plan.ready_for_apply is False
    assert any(
        diagnostic.code
        == "fundamental_revenue.snapshot_scope_manifest_invalid"
        for diagnostic in plan.diagnostics
    )


def test_plan_mops_snapshot_rejects_inconsistent_partial_scope_manifest(tmp_path) -> None:
    snapshot_file = tmp_path / "accepted_scope.csv"
    _write_mops_snapshot_csv(snapshot_file)
    availability_file = tmp_path / "monthly_revenue_availability.csv"
    _write_availability_csv(availability_file)
    manifest_file = tmp_path / "scope_manifest.json"
    manifest_file.write_text(
        '{"candidate_rows": 2, "accepted_rows": 2, "excluded_rows": 0, '
        '"excluded_keys": []}',
        encoding="utf-8",
    )

    plan = plan_mops_snapshot_monthly_revenue_backfill(
        snapshot_file=snapshot_file,
        availability_file=availability_file,
        source_version="mops-static-snapshot-monthly-revenue-2026-06-16",
        scope_manifest_file=manifest_file,
    )

    assert plan.ready_for_apply is False
    assert any(
        diagnostic.code
        == "fundamental_revenue.snapshot_scope_manifest_invalid"
        for diagnostic in plan.diagnostics
    )


def test_plan_mops_snapshot_rejects_mapping_earlier_than_capture_session(tmp_path) -> None:
    snapshot_file = tmp_path / "mops_snapshot.csv"
    _write_mops_snapshot_csv(snapshot_file, fetched_at="2026-06-16T00:00:00Z")
    availability_file = tmp_path / "monthly_revenue_availability.csv"
    _write_availability_csv(availability_file)

    plan = plan_mops_snapshot_monthly_revenue_backfill(
        snapshot_file=snapshot_file,
        availability_file=availability_file,
        source_version="mops-static-snapshot-monthly-revenue-2026-06-16",
    )

    assert plan.raw_row_count == 1
    assert len(plan.records) == 1
    assert plan.ready_for_apply is False
    assert any(
        diagnostic.code
        == "fundamental_availability.snapshot_capture_after_available_date"
        for diagnostic in plan.diagnostics
    )


def test_plan_mops_snapshot_rejects_missing_source_lineage(tmp_path) -> None:
    snapshot_file = tmp_path / "mops_snapshot.csv"
    _write_mops_snapshot_csv(snapshot_file)
    snapshot_file.write_text(
        snapshot_file.read_text(encoding="utf-8-sig").replace(
            "mops-static-2026-06-16", ""
        ),
        encoding="utf-8-sig",
    )


    availability_file = tmp_path / "monthly_revenue_availability.csv"
    _write_availability_csv(availability_file)

    plan = plan_mops_snapshot_monthly_revenue_backfill(
        snapshot_file=snapshot_file,
        availability_file=availability_file,
        source_version="mops-static-snapshot-monthly-revenue-2026-06-16",
    )

    assert plan.raw_row_count == 1
    assert plan.snapshot_invalid_row_count == 1
    assert plan.records == ()
    assert plan.ready_for_apply is False
    assert plan.diagnostics[0].code == "fundamental_revenue.snapshot_invalid_row"


def test_apply_monthly_revenue_backfill_inserts_records_and_backs_up_db(tmp_path) -> None:
    raw_dir = tmp_path / "financial_data"
    _write_revenue_csv(raw_dir)
    availability_file = tmp_path / "monthly_revenue_availability.csv"
    _write_availability_csv(availability_file)
    db_file = tmp_path / "twstock.db"
    backup_dir = tmp_path / "backup"
    with sqlite3.connect(db_file) as conn:
        apply_fundamental_schema(conn)

    result = apply_monthly_revenue_backfill(
        db_file=db_file,
        backup_dir=backup_dir,
        raw_dir=raw_dir,
        availability_file=availability_file,
        source_version="financial-data-csv-monthly-revenue-v1",
    )

    assert result.applied is True
    assert result.inserted_count == 1
    assert result.backup_file is not None
    assert result.backup_file.exists()
    with sqlite3.connect(db_file) as conn:
        rows = conn.execute(
            """
            SELECT stock_code, period, as_of_date, announced_date, available_date,
                   revenue, source, source_version, quality
            FROM fundamental_monthly_revenues
            """
        ).fetchall()
    assert rows == [
        (
            "2330",
            "2026-05",
            "2026-05-31",
            "2026-06-10",
            "2026-06-11",
            "1000000000",
            "financial_data.monthly_revenue_csv",
            "financial-data-csv-monthly-revenue-v1",
            "observed",
        )
    ]


def test_apply_mops_snapshot_preserves_prior_source_version(tmp_path) -> None:
    snapshot_file = tmp_path / "mops_snapshot.csv"
    _write_mops_snapshot_csv(snapshot_file)
    availability_file = tmp_path / "monthly_revenue_availability.csv"
    _write_availability_csv(availability_file)
    db_file = tmp_path / "twstock.db"
    with sqlite3.connect(db_file) as conn:
        apply_fundamental_schema(conn)
        conn.execute(
            """
            INSERT INTO fundamental_monthly_revenues(
                stock_code, period, as_of_date, announced_date, available_date,
                revenue, source, source_version, quality
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2330",
                "2026-05",
                "2026-05-31",
                "2026-06-10",
                "2026-06-11",
                "900",
                "mops.monthly_revenue_static_snapshot",
                "prior-capture-2026-06-11",
                "observed",
            ),
        )

    result = apply_mops_snapshot_monthly_revenue_backfill(
        db_file=db_file,
        backup_dir=tmp_path / "backup",
        snapshot_file=snapshot_file,
        availability_file=availability_file,
        source_version="capture-2026-06-11",
    )

    assert result.applied is True
    assert result.plan.formal_apply_eligible is True
    with sqlite3.connect(db_file) as conn:
        rows = conn.execute(
            "SELECT revenue, source_version FROM fundamental_monthly_revenues "
            "ORDER BY source_version"
        ).fetchall()
    assert len(rows) == 2
    assert {row[0] for row in rows} == {"900", "320000000000"}
    assert any(row[1] == "prior-capture-2026-06-11" for row in rows)


def test_apply_mops_snapshot_blocks_research_contract_before_backup_or_db_open(
    tmp_path, monkeypatch
) -> None:
    snapshot_file, availability_file, scope_file, _ = _write_openapi_full_scope_fixture(
        tmp_path
    )
    db_file = tmp_path / "twstock.db"
    with sqlite3.connect(db_file) as conn:
        apply_fundamental_schema(conn)
    db_hash_before = hashlib.sha256(db_file.read_bytes()).hexdigest()
    backup_dir = tmp_path / "backup"

    def forbidden_backup(*_args, **_kwargs):
        pytest.fail("research-only source reached the backup writer")

    def forbidden_connect(*_args, **_kwargs):
        pytest.fail("research-only source opened the production database")

    monkeypatch.setattr(
        backfill_module,
        "_create_consistent_sqlite_backup",
        forbidden_backup,
    )
    monkeypatch.setattr(backfill_module.sqlite3, "connect", forbidden_connect)

    result = apply_mops_snapshot_monthly_revenue_backfill(
        db_file=db_file,
        backup_dir=backup_dir,
        snapshot_file=snapshot_file,
        availability_file=availability_file,
        source_version="monthly-revenue-openapi-research-2026-08",
        scope_manifest_file=scope_file,
    )

    assert result.applied is False
    assert result.inserted_count == 0
    assert result.backup_file is None
    assert result.plan.ready_for_apply is True
    assert result.plan.formal_apply_eligible is False
    assert "no hash-bound source/unit acceptance receipt" in str(
        result.plan.formal_apply_blocked_reason
    )
    assert backup_dir.exists() is False
    assert hashlib.sha256(db_file.read_bytes()).hexdigest() == db_hash_before


def test_apply_monthly_revenue_backfill_refuses_diagnostics(tmp_path) -> None:
    raw_dir = tmp_path / "financial_data"
    _write_revenue_csv(raw_dir)
    db_file = tmp_path / "twstock.db"
    with sqlite3.connect(db_file) as conn:
        apply_fundamental_schema(conn)

    result = apply_monthly_revenue_backfill(
        db_file=db_file,
        backup_dir=tmp_path / "backup",
        raw_dir=raw_dir,
        availability_file=tmp_path / "missing.csv",
        source_version="financial-data-csv-monthly-revenue-v1",
    )

    assert result.applied is False
    assert result.inserted_count == 0
    assert result.backup_file is None
    with sqlite3.connect(db_file) as conn:
        count = conn.execute("SELECT COUNT(*) FROM fundamental_monthly_revenues").fetchone()[0]
    assert count == 0


def test_monthly_revenue_backup_captures_committed_wal_state(tmp_path) -> None:
    db_file = tmp_path / "twstock.db"
    backup_dir = tmp_path / "task_backup"
    writer = sqlite3.connect(db_file)
    try:
        conn = writer
        apply_fundamental_schema(conn)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA wal_autocheckpoint=0")
        conn.execute(
            """
            INSERT INTO fundamental_monthly_revenues(
                stock_code, period, as_of_date, announced_date, available_date,
                revenue, source, source_version, quality
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2330",
                "2026-05",
                "2026-05-31",
                "2026-06-10",
                "2026-06-11",
                "100",
                "fixture",
                "wal-v1",
                "observed",
            ),
        )
        conn.commit()
        wal_file = db_file.with_name(f"{db_file.name}-wal")
        assert wal_file.exists()
        assert wal_file.stat().st_size > 0

        backup_file = backfill_module._create_consistent_sqlite_backup(
            db_file,
            backup_dir,
            label="wal-test",
        )

        assert backup_file is not None
        verification = sqlite3.connect(backup_file)
        try:
            assert verification.execute(
                "SELECT revenue FROM fundamental_monthly_revenues"
            ).fetchone() == ("100",)
            assert verification.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        finally:
            verification.close()
    finally:
        writer.close()


def test_monthly_revenue_apply_rolls_back_transaction_without_restoring_whole_db(
    tmp_path,
    monkeypatch,
) -> None:
    raw_dir = tmp_path / "financial_data"
    _write_revenue_csv(raw_dir)
    availability_file = tmp_path / "monthly_revenue_availability.csv"
    _write_availability_csv(availability_file)
    db_file = tmp_path / "twstock.db"
    backup_dir = tmp_path / "task_backup"
    with sqlite3.connect(db_file) as conn:
        apply_fundamental_schema(conn)
        conn.execute("CREATE TABLE unrelated_state (value TEXT NOT NULL)")
        conn.execute("INSERT INTO unrelated_state(value) VALUES ('keep')")

    def _fail_after_partial_insert(conn, records):
        conn.execute(
            """
            INSERT INTO fundamental_monthly_revenues(
                stock_code, period, as_of_date, announced_date, available_date,
                revenue, source, source_version, quality
            )
            VALUES ('2330', '2026-05', '2026-05-31', '2026-06-10',
                    '2026-06-11', '999', 'fixture', 'partial-failure', 'observed')
            """
        )
        raise RuntimeError("injected writer failure")

    monkeypatch.setattr(
        backfill_module,
        "_insert_monthly_revenue_records",
        _fail_after_partial_insert,
    )
    real_backup = backfill_module._create_consistent_sqlite_backup

    def _backup_then_commit_after_backup(*args, **kwargs):
        backup_file = real_backup(*args, **kwargs)
        with sqlite3.connect(db_file) as concurrent:
            concurrent.execute(
                "INSERT INTO unrelated_state(value) VALUES ('after-backup')"
            )
        return backup_file

    monkeypatch.setattr(
        backfill_module,
        "_create_consistent_sqlite_backup",
        _backup_then_commit_after_backup,
    )

    try:
        apply_monthly_revenue_backfill(
            db_file=db_file,
            backup_dir=backup_dir,
            raw_dir=raw_dir,
            availability_file=availability_file,
            source_version="financial-data-csv-monthly-revenue-v1",
        )
    except RuntimeError as exc:
        assert str(exc) == "injected writer failure"
    else:
        raise AssertionError("injected writer failure was not raised")

    with sqlite3.connect(db_file) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM fundamental_monthly_revenues"
        ).fetchone() == (0,)
        assert conn.execute(
            "SELECT value FROM unrelated_state"
        ).fetchone() == ("keep",)
        assert [
            row[0]
            for row in conn.execute(
                "SELECT value FROM unrelated_state ORDER BY rowid"
            ).fetchall()
        ] == ["keep", "after-backup"]
    assert len(list(backup_dir.glob("*.db"))) == 1
