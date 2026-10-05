from __future__ import annotations

import csv
from datetime import date, datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sqlite3

import pytest

from data_module.current_observed_market_ownership_reader import (
    MAX_TDCC_CAPTURE_DIRS_TO_INSPECT,
    read_current_observed_market_ownership,
)
from data_module.tdcc_shareholding_candidate import (
    TDCC_FIELDS,
    TDCC_SOURCE_VERSION,
    TDCC_URL,
    normalize_tdcc_payload,
)


READ_AT = datetime(2026, 10, 5, 2, 0, tzinfo=timezone.utc)
REPORT_DAY = "2026-10-02"


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _flow_row(
    source: str,
    *,
    stock_code: str,
    decision_date: str,
    source_version: str,
    value: int,
    available_at: str = "2026-10-05T01:00:00Z",
) -> dict[str, object]:
    common: dict[str, object] = {
        "stock_code": stock_code,
        "decision_date": decision_date,
        "source_version": source_version,
        "publication_at": None,
        "first_observed_at": available_at,
        "available_at": available_at,
        "available_date": None,
        "quality": "degraded",
    }
    if source == "institutional":
        return {
            **common,
            "foreign_investor_buy": value,
            "foreign_investor_sell": value,
            "foreign_investor_net": 0,
            "investment_trust_buy": value,
            "investment_trust_sell": value,
            "investment_trust_net": 0,
            "dealer_buy": value,
            "dealer_sell": value,
            "dealer_net": 0,
        }
    if source == "credit":
        return {
            **common,
            "margin_purchase": value,
            "margin_balance": value,
            "short_sale": value,
            "short_balance": value,
            "financing": value,
            "securities_lending": value,
        }
    raise AssertionError(source)


def _create_flow_db(path: Path, sources: tuple[str, ...]) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE phase3c_source_observations (
            source TEXT NOT NULL,
            decision_date TEXT NOT NULL,
            observation_hash TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            observation_mode TEXT NOT NULL,
            source_versions TEXT NOT NULL,
            first_observed_at_min TEXT,
            available_at_max TEXT,
            canonical_payload_json TEXT NOT NULL,
            diagnostic_json TEXT,
            PRIMARY KEY (source, decision_date, observation_hash)
        );
        """
    )
    if "institutional" in sources:
        conn.execute(
            """CREATE TABLE institutional_flows (
                stock_code TEXT NOT NULL, decision_date TEXT NOT NULL,
                source_version TEXT NOT NULL, publication_at TEXT,
                first_observed_at TEXT NOT NULL, available_at TEXT NOT NULL,
                available_date TEXT, quality TEXT NOT NULL,
                foreign_investor_buy INTEGER NOT NULL,
                foreign_investor_sell INTEGER NOT NULL,
                foreign_investor_net INTEGER NOT NULL,
                investment_trust_buy INTEGER NOT NULL,
                investment_trust_sell INTEGER NOT NULL,
                investment_trust_net INTEGER NOT NULL,
                dealer_buy INTEGER NOT NULL, dealer_sell INTEGER NOT NULL,
                dealer_net INTEGER NOT NULL,
                PRIMARY KEY(stock_code, decision_date)
            )"""
        )
    if "credit" in sources:
        conn.execute(
            """CREATE TABLE credit_transactions (
                stock_code TEXT NOT NULL, decision_date TEXT NOT NULL,
                source_version TEXT NOT NULL, publication_at TEXT,
                first_observed_at TEXT NOT NULL, available_at TEXT NOT NULL,
                available_date TEXT, quality TEXT NOT NULL,
                margin_purchase INTEGER NOT NULL, margin_balance INTEGER NOT NULL,
                short_sale INTEGER NOT NULL, short_balance INTEGER NOT NULL,
                financing INTEGER, securities_lending INTEGER,
                PRIMARY KEY(stock_code, decision_date)
            )"""
        )
    return conn


def _insert_candidate_rows(conn: sqlite3.Connection, source: str, rows: list[dict[str, object]]) -> None:
    table = "institutional_flows" if source == "institutional" else "credit_transactions"
    columns = [str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')]
    placeholders = ",".join("?" for _ in columns)
    conn.executemany(
        f'INSERT INTO "{table}" ({",".join(columns)}) VALUES ({placeholders})',
        [[row.get(column) for column in columns] for row in rows],
    )


def _insert_observation(
    conn: sqlite3.Connection,
    source: str,
    rows: list[dict[str, object]],
    observed_at: str,
    *,
    payload_clock: str | None = None,
    row_count: int | None = None,
    observation_hash: str | None = None,
    observation_mode: str = "new_observation_reconciled",
) -> str:
    day = str(rows[0]["decision_date"])
    versions = sorted({str(row["source_version"]) for row in rows})
    payload = {
        "schema_version": "phase3c-canonical-observation.v1",
        "observation_at": payload_clock or observed_at,
        "rows": rows,
    }
    payload_text = _canonical_json(payload)
    digest = "sha256:" + hashlib.sha256(payload_text.encode("utf-8")).hexdigest()
    stored_hash = observation_hash or digest
    diagnostic = {
        "status": "RECONCILED",
        "observation_hash": stored_hash,
        "decision_date": day,
        "expected_row_count": len(rows) if row_count is None else row_count,
        "observation_at": observed_at,
    }
    conn.execute(
        """INSERT INTO phase3c_source_observations (
            source,decision_date,observation_hash,observed_at,row_count,
            observation_mode,source_versions,first_observed_at_min,
            available_at_max,canonical_payload_json,diagnostic_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            source,
            day,
            stored_hash,
            observed_at,
            len(rows) if row_count is None else row_count,
            observation_mode,
            json.dumps(versions, separators=(",", ":")),
            min(str(row["first_observed_at"]) for row in rows),
            max(str(row["available_at"]) for row in rows),
            payload_text,
            _canonical_json(diagnostic),
        ),
    )
    return stored_hash


def _read(
    *,
    stock_code: str = "2330",
    cutoff: date = date(2026, 10, 2),
    observed_at: datetime = READ_AT,
    candidate_db: Path | None = None,
    capture_root: Path | None = None,
    readback_clock=None,
):
    return read_current_observed_market_ownership(
        stock_code=stock_code,
        cutoff=cutoff,
        observed_at=observed_at,
        candidate_db_file=candidate_db,
        capture_root=capture_root,
        readback_clock=readback_clock,
    )


def _write_tdcc_payload(report_date: str, symbols: tuple[str, ...], blocked: frozenset[str] = frozenset()) -> bytes:
    rows: list[list[str]] = []
    for symbol in symbols:
        ratios = ["1.00"] * 16
        ratios[0] = "2.00"
        ratios[1] = "3.00"
        ratios[14] = "83.00"
        ratios[15] = "0.00"
        if symbol in blocked:
            ratios[5] = "20.00"
        for tier, ratio in enumerate(ratios, 1):
            rows.append([report_date, symbol, str(tier), "10", "100", ratio])
        rows.append([report_date, symbol, "17", "10", "1000", "100.00"])
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(TDCC_FIELDS)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8-sig")


def _write_csv(path: Path, rows: list[dict[str, object]], *, fieldnames: list[str] | None = None) -> bytes:
    if fieldnames is None:
        fieldnames = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path.read_bytes()


def _write_tdcc_capture(
    capture_root: Path,
    *,
    run_id: str = "run_20261005_0001",
    report_date: str = "20261002",
    symbols: tuple[str, ...] = ("2330",),
    blocked: frozenset[str] = frozenset(),
    completed_at: str = "2026-10-05T01:05:00Z",
    aggregate_subset: bool = False,
    aggregate_padding_bytes: int = 0,
) -> tuple[Path, Path, bytes]:
    from datetime import datetime as _datetime

    directory = capture_root / "tdcc" / run_id
    directory.mkdir(parents=True, exist_ok=True)
    raw_name = f"tdcc_1-5_raw_{report_date}.csv"
    tier_name = f"tdcc_1-5_{report_date}_tiers.csv"
    aggregate_name = f"tdcc_1-5_{report_date}_aggregate.csv"
    manifest_name = f"tdcc_1-5_{report_date}_manifest.json"
    raw_bytes = _write_tdcc_payload(report_date, symbols, blocked)
    raw_path = directory / raw_name
    raw_path.write_bytes(raw_bytes)
    observed_clock = _datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
    replay = normalize_tdcc_payload(raw_bytes, observed_at=observed_clock)
    tiers = [dict(row) for row in replay.tier_rows]
    aggregates = [dict(row) for row in replay.aggregate_rows]
    if aggregate_subset:
        aggregates = [row for row in aggregates if row["candidate_status"] == "shadow_ready"]
    tier_bytes = _write_csv(directory / tier_name, tiers)
    aggregate_rows: list[dict[str, object]] = [dict(row) for row in aggregates]
    if aggregate_padding_bytes:
        for index, row in enumerate(aggregate_rows):
            # 總檔案超過舊上限，單一欄位仍符合 CSV parser 的既有上限。
            for part in range((aggregate_padding_bytes + 65535) // 65536):
                size = min(65536, aggregate_padding_bytes - part * 65536)
                row[f"fixture_padding_{part}"] = "x" * size if index == 0 else ""
    aggregate_fields = list(aggregate_rows[0]) if aggregate_rows else []
    aggregate_bytes = _write_csv(directory / aggregate_name, aggregate_rows, fieldnames=aggregate_fields)
    raw_sha = hashlib.sha256(raw_bytes).hexdigest()
    manifest = {
        "schema_version": "tdcc-current-ownership-capture.v1",
        "capture_id": run_id,
        "source_id": "tdcc_shareholding",
        "source_version": TDCC_SOURCE_VERSION,
        "endpoint": TDCC_URL,
        "candidate_only": True,
        "formal_db_written": False,
        "downstream_eligibility": "none",
        "publication_at": None,
        "availability_policy": "first_observed_only",
        "report_date": replay.report_date,
        "request_started_at_utc": "2026-10-05T01:00:00Z",
        "body_completed_at_utc": completed_at,
        "raw_file": raw_name,
        "source_payload_sha256": raw_sha,
        "capture_metadata": {
            "http_status": 200,
            "sha256": raw_sha,
            "content_length": len(raw_bytes),
            "raw_file": raw_name,
            "url": TDCC_URL,
        },
        "full_tier_file": tier_name,
        "artifact_hashes": {
            tier_name: hashlib.sha256(tier_bytes).hexdigest(),
            aggregate_name: hashlib.sha256(aggregate_bytes).hexdigest(),
        },
    }
    manifest_path = directory / manifest_name
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    # A smaller ready subset may exist beside the full aggregate. It is never
    # substituted into the manifest's full-artifact binding.
    ready_rows = [dict(row) for row in replay.aggregate_rows if row["candidate_status"] == "shadow_ready"]
    _write_csv(directory / f"tdcc_1-5_{report_date}_ready_import.csv", ready_rows)
    return directory, manifest_path, raw_bytes


def test_phase3c_selects_latest_day_and_clock_group_and_preserves_zero(tmp_path: Path) -> None:
    db = tmp_path / "candidate.db"
    conn = _create_flow_db(db, ("institutional",))
    old = _flow_row(
        "institutional", stock_code="2330", decision_date="2026-10-01",
        source_version="twse-official-T86", value=91,
    )
    early = _flow_row(
        "institutional", stock_code="2330", decision_date=REPORT_DAY,
        source_version="twse-official-T86", value=7,
    )
    latest = _flow_row(
        "institutional", stock_code="2330", decision_date=REPORT_DAY,
        source_version="twse-official-T86", value=0,
    )
    latest_clock = "2026-10-05T01:30:00Z"
    _insert_candidate_rows(conn, "institutional", [old, latest])
    _insert_observation(conn, "institutional", [old], "2026-10-01T14:00:00Z")
    _insert_observation(conn, "institutional", [early], "2026-10-05T01:00:00Z")
    _insert_observation(conn, "institutional", [latest], latest_clock)
    # Two encodings of the same aware instant are distinct hashes, but their
    # identical latest rows are a valid same-clock tie group.
    _insert_observation(
        conn, "institutional", [latest], latest_clock,
        payload_clock="2026-10-05T09:30:00+08:00",
    )
    conn.commit()
    conn.close()
    before = hashlib.sha256(db.read_bytes()).hexdigest()

    result = _read(candidate_db=db)

    observation = result.observations["institutional"]
    assert observation.data_as_of == REPORT_DAY
    assert observation.values["foreign_investor_buy"] == 0
    assert observation.values["foreign_investor_net"] == 0
    assert observation.row_count == 9
    assert observation.quantity_unit == "shares"
    assert observation.custody_kind == "normalized_custody"
    assert "historical PIT and formal eligibility are false" in " ".join(observation.limitations)
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


def test_phase3c_older_conflict_does_not_poison_valid_latest_but_bad_latest_never_falls_back(tmp_path: Path) -> None:
    db = tmp_path / "candidate.db"
    conn = _create_flow_db(db, ("institutional",))
    old = _flow_row(
        "institutional", stock_code="2330", decision_date="2026-10-01",
        source_version="twse-official-T86", value=5,
    )
    latest = _flow_row(
        "institutional", stock_code="2330", decision_date=REPORT_DAY,
        source_version="twse-official-T86", value=0,
    )
    _insert_candidate_rows(conn, "institutional", [old, latest])
    old_hash = _insert_observation(conn, "institutional", [old], "2026-10-01T12:00:00Z")
    latest_hash = _insert_observation(conn, "institutional", [latest], "2026-10-05T01:30:00Z")
    # The older row's custody is corrupt; it is outside the selected metadata
    # group and must not block a valid newer observation.
    conn.execute(
        "UPDATE phase3c_source_observations SET observation_hash=? WHERE decision_date=?",
        ("sha256:" + "a" * 64, "2026-10-01"),
    )
    conn.commit()
    conn.close()

    good = _read(candidate_db=db)
    assert good.observations["institutional"].data_as_of == REPORT_DAY
    assert good.observations["institutional"].custody_sha256 == latest_hash

    conn = sqlite3.connect(db)
    payload_row = conn.execute(
        "SELECT canonical_payload_json FROM phase3c_source_observations WHERE observation_hash=?",
        (latest_hash,),
    ).fetchone()
    payload = json.loads(payload_row[0])
    payload["rows"][0]["foreign_investor_buy"] = 44
    changed_text = _canonical_json(payload)
    # Leave the stored digest unchanged so the newest selected observation is
    # tampered. A valid older row must not become a fallback.
    conn.execute(
        "UPDATE phase3c_source_observations SET canonical_payload_json=? WHERE observation_hash=?",
        (changed_text, latest_hash),
    )
    conn.commit()
    conn.close()

    rejected = _read(candidate_db=db)
    assert "institutional" not in rejected.observations
    assert "normalized observation hash mismatch" in rejected.diagnostics["institutional"]
    assert old_hash


@pytest.mark.parametrize("defect", ["hash", "row_count", "stock", "version", "table"])
def test_phase3c_latest_identity_and_table_mismatches_are_rejected(tmp_path: Path, defect: str) -> None:
    db = tmp_path / f"{defect}.db"
    conn = _create_flow_db(db, ("credit",))
    version = "not-a-supported-credit-version" if defect == "version" else "tpex-mainboard-margin-openapi.v1"
    row = _flow_row(
        "credit", stock_code="2330", decision_date=REPORT_DAY,
        source_version=version, value=0,
    )
    _insert_candidate_rows(conn, "credit", [row])
    digest = _insert_observation(conn, "credit", [row], "2026-10-05T01:30:00Z")
    if defect == "hash":
        conn.execute(
            "UPDATE phase3c_source_observations SET observation_hash=? WHERE observation_hash=?",
            ("sha256:" + "0" * 64, digest),
        )
    elif defect == "row_count":
        conn.execute(
            "UPDATE phase3c_source_observations SET row_count=2 WHERE observation_hash=?",
            (digest,),
        )
    elif defect == "stock":
        conn.execute("UPDATE credit_transactions SET stock_code='9999' WHERE stock_code='2330'")
    elif defect == "table":
        conn.execute("UPDATE credit_transactions SET margin_purchase=19 WHERE stock_code='2330'")
    conn.commit()
    conn.close()

    result = _read(candidate_db=db)

    assert "credit" not in result.observations
    assert "credit" in result.diagnostics
    assert "rejected" in result.diagnostics["credit"] or "latest" in result.diagnostics["credit"]


def test_phase3c_rejects_future_or_naive_observation_clocks(tmp_path: Path) -> None:
    db = tmp_path / "future.db"
    conn = _create_flow_db(db, ("institutional",))
    future = _flow_row(
        "institutional", stock_code="2330", decision_date=REPORT_DAY,
        source_version="twse-official-T86", value=1,
    )
    _insert_candidate_rows(conn, "institutional", [future])
    _insert_observation(conn, "institutional", [future], "2026-10-05T03:00:00Z")
    conn.commit()
    conn.close()

    result = _read(candidate_db=db, observed_at=READ_AT)
    assert "institutional" not in result.observations
    assert "from the future" in result.diagnostics["institutional"]
    with pytest.raises(ValueError, match="timezone-aware"):
        _read(candidate_db=db, observed_at=datetime(2026, 10, 5, 2, 0))


def test_credit_source_versions_keep_their_actual_units_and_zero_values(tmp_path: Path) -> None:
    db = tmp_path / "credit.db"
    conn = _create_flow_db(db, ("credit",))
    rows = [
        _flow_row(
            "credit", stock_code="2330", decision_date=REPORT_DAY,
            source_version="tpex-mainboard-margin-openapi.v1", value=0,
        ),
        _flow_row(
            "credit", stock_code="2317", decision_date=REPORT_DAY,
            source_version="twse-official-MI_MARGN", value=0,
        ),
        _flow_row(
            "credit", stock_code="2603", decision_date=REPORT_DAY,
            source_version="tpex-official-margin_bal", value=0,
        ),
    ]
    _insert_candidate_rows(conn, "credit", rows)
    _insert_observation(conn, "credit", rows, "2026-10-05T01:30:00Z")
    conn.commit()
    conn.close()

    actual = {
        code: _read(stock_code=code, candidate_db=db).observations["credit"]
        for code in ("2330", "2317", "2603")
    }
    assert actual["2330"].source_version == "tpex-mainboard-margin-openapi.v1"
    assert actual["2330"].quantity_unit == "shares"
    assert actual["2317"].quantity_unit == "trading_units"
    assert actual["2603"].quantity_unit == "lots"
    assert actual["2330"].values["margin_purchase"] == 0
    assert actual["2330"].values["financing"] == 0
    assert all(type(item) is int for item in actual["2330"].values.values())


def test_tdcc_full_aggregate_over_16mib_replays_raw_and_preserves_blocked_peer(tmp_path: Path) -> None:
    capture_root = tmp_path / "source"
    directory, manifest, raw = _write_tdcc_capture(
        capture_root,
        symbols=("2330", "2317"),
        blocked=frozenset({"2317"}),
        aggregate_padding_bytes=17 * 1024 * 1024,
    )
    aggregate_path = directory / "tdcc_1-5_20261002_aggregate.csv"
    with aggregate_path.open("r", encoding="utf-8-sig", newline="") as handle:
        full_rows = list(csv.DictReader(handle))
    with (directory / "tdcc_1-5_20261002_ready_import.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        ready_rows = list(csv.DictReader(handle))
    assert len(raw) < 32 * 1024 * 1024
    assert aggregate_path.stat().st_size > 16 * 1024 * 1024
    assert len(full_rows) == 2
    assert len(ready_rows) == 1
    assert {row["candidate_status"] for row in full_rows} == {"shadow_ready", "blocked"}

    result = _read(
        stock_code="2330",
        capture_root=capture_root,
        readback_clock=lambda: READ_AT,
    )

    tdcc = result.observations["tdcc"]
    assert tdcc.stock_code == "2330"
    assert tdcc.data_as_of == REPORT_DAY
    assert tdcc.custody_kind == "raw_capture_replayed"
    assert tdcc.custody_sha256 == hashlib.sha256(raw).hexdigest()
    assert len(json.loads(str(tdcc.values["shareholding_tiers"]))) == 17
    assert "publication timestamp is unknown" in " ".join(tdcc.limitations)
    assert manifest.is_file()


@pytest.mark.parametrize("defect", ["wrong_stock", "period", "source", "hash", "future_completion", "missing_raw", "missing_aggregate", "ready_subset", "naive_readback"])
def test_tdcc_invalid_identity_or_custody_is_not_reported_as_observed(tmp_path: Path, defect: str) -> None:
    capture_root = tmp_path / "source"
    directory, manifest_path, raw = _write_tdcc_capture(capture_root, symbols=("2330",))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    aggregate_path = directory / "tdcc_1-5_20261002_aggregate.csv"
    raw_path = directory / manifest["raw_file"]
    cutoff = date(2026, 10, 2)
    readback = lambda: datetime(2026, 10, 5, 1, 10, tzinfo=timezone.utc)
    stock_code = "2330"
    if defect == "wrong_stock":
        stock_code = "9999"
    elif defect == "period":
        cutoff = date(2026, 10, 1)
    elif defect == "source":
        manifest["source_id"] = "other_source"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    elif defect == "hash":
        raw_path.write_bytes(raw + b"tamper")
    elif defect == "future_completion":
        manifest["body_completed_at_utc"] = "2026-10-05T01:11:00Z"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    elif defect == "missing_raw":
        raw_path.unlink()
    elif defect == "missing_aggregate":
        aggregate_path.unlink()
    elif defect == "ready_subset":
        with aggregate_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        subset = [row for row in rows if row["candidate_status"] == "shadow_ready"]
        fields = list(rows[0])
        aggregate_bytes = _write_csv(aggregate_path, subset, fieldnames=fields)
        manifest["artifact_hashes"][aggregate_path.name] = hashlib.sha256(aggregate_bytes).hexdigest()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    elif defect == "naive_readback":
        readback = lambda: datetime(2026, 10, 5, 1, 10)

    result = _read(
        stock_code=stock_code,
        cutoff=cutoff,
        capture_root=capture_root,
        readback_clock=readback,
    )

    assert "tdcc" not in result.observations
    assert "tdcc" in result.diagnostics


def test_tdcc_capture_history_over_32_selects_newest_and_never_falls_back_from_invalid_newest(tmp_path: Path) -> None:
    capture_root = tmp_path / "source"
    tdcc_root = capture_root / "tdcc"
    tdcc_root.mkdir(parents=True)
    for index in range(MAX_TDCC_CAPTURE_DIRS_TO_INSPECT + 1):
        (tdcc_root / f"run_20261005_{index:02d}").mkdir()
    newest_dir, newest_manifest, _ = _write_tdcc_capture(
        capture_root,
        run_id=f"run_20261005_{MAX_TDCC_CAPTURE_DIRS_TO_INSPECT:02d}",
        report_date="20261002",
    )
    assert newest_dir == tdcc_root / f"run_20261005_{MAX_TDCC_CAPTURE_DIRS_TO_INSPECT:02d}"
    result = _read(capture_root=capture_root, readback_clock=lambda: READ_AT)
    assert result.observations["tdcc"].data_as_of == REPORT_DAY

    old_dir, _, _ = _write_tdcc_capture(
        capture_root, run_id="run_20261004_older", report_date="20260925"
    )
    assert old_dir.exists()
    manifest = json.loads(newest_manifest.read_text(encoding="utf-8"))
    newest_raw = newest_dir / manifest["raw_file"]
    newest_raw.write_bytes(newest_raw.read_bytes() + b"changed")
    failed = _read(capture_root=capture_root, readback_clock=lambda: READ_AT)
    assert "tdcc" not in failed.observations
    assert "TDCC raw bytes do not match" in failed.diagnostics["tdcc"]
