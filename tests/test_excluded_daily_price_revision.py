from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from data_module import excluded_daily_price_revision as exclusions
from scripts import repair_excluded_daily_prices as repair


MISSING_SYMBOLS = (
    "0054", "0058", "0059", "1262", "1435", "1469", "1507", "1589", "1592",
    "1701", "1704", "1724", "1902", "2311", "2325", "2358", "2443", "2448",
    "2456", "2475", "2499", "2809", "2823", "2841", "2856", "2888", "2936",
    "3383", "3454", "3514", "3519", "3536", "3561", "3579", "3682", "3698",
    "4141", "4144", "4725", "4984", "5259", "5264", "5305", "6131", "6145",
    "6172", "6251", "6289", "6422", "6452", "8427", "8480", "9157", "9188",
)


def _write_json(path: Path, value: object) -> bytes:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return body


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _official_url(venue: str, day: str) -> str:
    if venue == "twse":
        return f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={day}&type=ALL&response=json"
    return (
        "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc?"
        f"date={day[:4]}%2F{day[4:6]}%2F{day[6:]}&type=EW&response=json"
    )


def _write_evidence_archive(root: Path) -> Path:
    archive_dir = root / exclusions.SOURCE_DIR / "fixture01"
    archive_dir.mkdir(parents=True, exist_ok=True)
    expected_twse_fields = [
        "證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額", "開盤價", "最高價",
        "最低價", "收盤價", "漲跌(+/-)", "漲跌價差", "最後揭示買價", "最後揭示買量",
        "最後揭示賣價", "最後揭示賣量", "本益比",
    ]
    tpex_fields = ["代號", "名稱", *[f"欄位{i}" for i in range(15)]]
    twse_codes = [f"W{i:05d}" for i in range(31124)]
    tpex_codes = [f"P{i:04d}" for i in range(1007)]
    payloads: dict[tuple[str, str], dict[str, object]] = {}
    for day in exclusions.OFFICIAL_DATES:
        for venue in ("twse", "tpex"):
            if day in exclusions.CLOSED_DATES and venue == "twse":
                payload: dict[str, object] = {"stat": "很抱歉，沒有符合條件的資料!", "type": "ALL"}
            elif venue == "twse":
                rows = [[code, *["" for _ in range(15)]] for code in twse_codes]
                payload = {
                    "stat": "OK",
                    "type": "ALL",
                    "date": day,
                    "tables": [{
                        "title": "115年05月20日 每日收盤行情(全部)",
                        "fields": expected_twse_fields,
                        "data": rows,
                    }],
                }
            else:
                roc_date = exclusions._CLOSURE_TPEX_ROC[day]
                if day in exclusions.CLOSED_DATES:
                    payload = {
                        "stat": "ok", "date": day,
                        "tables": [{
                            "title": "上櫃股票每日收盤行情(不含定價)",
                            "date": roc_date, "totalCount": 0, "fields": tpex_fields, "data": [],
                        }],
                    }
                else:
                    rows = [[code, *["" for _ in range(16)]] for code in tpex_codes]
                    payload = {
                        "stat": "ok", "date": day,
                        "tables": [{
                            "title": "上櫃股票每日收盤行情(不含定價)",
                            "date": roc_date, "totalCount": 1007, "fields": tpex_fields, "data": rows,
                        }],
                    }
            payloads[(venue, day)] = payload

    entries = []
    for day in exclusions.OFFICIAL_DATES:
        for venue in ("twse", "tpex"):
            body = json.dumps(payloads[(venue, day)], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            payload_name = f"{venue}-{day}.json"
            payload_path = archive_dir / payload_name
            payload_path.write_bytes(body)
            captured_at = f"2026-09-23T22:{day[-2:]}:{'11' if venue == 'tpex' else '08'}.000000+00:00"
            url = _official_url(venue, day)
            receipt = {
                "venue": venue,
                "date": day,
                "url": url,
                "http_status": 200,
                "captured_at": captured_at,
                "sha256": _hash(body),
                "historical_pit": False,
            }
            receipt_bytes = _write_json(archive_dir / f"{venue}-{day}.receipt.json", receipt)
            for name, data in ((payload_name, body), (f"{venue}-{day}.receipt.json", receipt_bytes)):
                source_path = archive_dir / name
                entries.append({
                    "source": f"official-capture://{name}",
                    "archived": str(source_path.resolve()),
                    "sha256": _hash(data),
                    "bytes": len(data),
                })
    _write_json(
        archive_dir / "archive.json",
        {"archived_at": "2026-09-23T22:01:00+00:00", "historical_pit": False, "files": entries},
    )
    return archive_dir


def _write_market_receipt(root: Path, database_path: Path, run_id: str) -> Path:
    source_dir = root / "output/scheduled/formal_market_repair_sources" / run_id
    source_dir.mkdir(parents=True, exist_ok=True)
    months = ["201602", "202410", "202509"]
    rows = {
        "2016-02-10": {"收盤指數": "8000"},
        "2024-10-01": {"收盤指數": "22000"},
        "2025-09-30": {"收盤指數": "25000"},
    }
    capture = {
        "schema_version": "official-market-source-capture.v1",
        "months": months,
        "receipts": [
            {"month": month, "report": report}
            for month in months for report in ("FMTQIK", "MI_5MINS_HIST")
        ],
        "rows": rows,
    }
    capture_path = source_dir / "capture.json"
    capture_sha = _hash(_write_json(capture_path, capture))
    market_dir = root / exclusions.RECEIPT_DIR / "formal_market" / run_id
    market_plan = {
        "schema_version": "formal-market-repair.v1",
        "database_path": str(database_path.resolve()),
        "sources": [{"path": str(capture_path.resolve()), "sha256": capture_sha}],
        "after": {"rows": [
            {"日期": "20160210", "指數名稱": "TAIEX"},
            {"日期": "20241001", "指數名稱": "TAIEX"},
            {"日期": "20250930", "指數名稱": "TAIEX"},
        ]},
    }
    plan_bytes = _write_json(market_dir / "plan.json", market_plan)
    plan_sha = _hash(plan_bytes)
    journal_bytes = _write_json(
        market_dir / "journal.json",
        {"schema_version": "formal-market-repair.v1", "state": "prepared", "plan_sha256": plan_sha},
    )
    del journal_bytes
    receipt_bytes = _write_json(
        market_dir / "receipt.json",
        {"schema_version": "formal-market-repair.v1", "state": "applied", "plan_sha256": plan_sha},
    )
    _write_json(
        market_dir / "revision.json",
        {
            "schema_version": "formal-market-revision.v1",
            "state": "applied",
            "database_path": str(database_path.resolve()),
            "plan_sha256": plan_sha,
            "receipt_sha256": _hash(receipt_bytes),
        },
    )
    return market_dir


@pytest.fixture
def evidence_root(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "FA_Data"
    root.mkdir(parents=True)
    return root, _write_evidence_archive(root)


def _make_database(root: Path, name: str) -> Path:
    sqlite_dir = root / "sqlite"
    sqlite_dir.mkdir(parents=True, exist_ok=True)
    path = sqlite_dir / f"{name}.db"
    connection = sqlite3.connect(path)
    for table in ("daily_prices", "technical_indicators"):
        connection.execute(
            f'CREATE TABLE "{table}"('
            '"日期" TEXT NOT NULL, "證券代號" TEXT NOT NULL, "成交股數" INTEGER, '
            '"開盤價" REAL, "最高價" REAL, "最低價" REAL, "收盤價" REAL, '
            'PRIMARY KEY("日期", "證券代號"))'
        )
    rows: list[tuple[str, str, int, float, float, float, float]] = []
    for day, symbol in (("20160211", "CLOSE1"), ("20250929", "CLOSE2")):
        rows.append((day, symbol, 100, 10, 11, 9, 10))
    for index, symbol in enumerate(MISSING_SYMBOLS):
        value = ("20260520", symbol, 100, 10, 11, 9, 10)
        rows.append(value)
        rows.append(("20241002", symbol, *value[2:]))
        older = value if index < 50 else ("20171218", symbol, 100, 10, 11, 9, 11)
        if index < 50:
            older = ("20171218", symbol, *value[2:])
        rows.append(older)
    for table in ("daily_prices", "technical_indicators"):
        connection.executemany(f'INSERT INTO "{table}" VALUES (?,?,?,?,?,?,?)', rows)
    connection.commit()
    connection.close()
    return path


def _scope_plan(
    root: Path, database_path: Path, evidence_dir: Path, market_dir: Path, run_id: str,
) -> tuple[dict[str, object], dict[str, object]]:
    original_market_validator = exclusions._validate_market_chain
    market_validation = original_market_validator(
        database_path, root, market_dir.relative_to(root).as_posix(), full_source_validation=False,
    )
    # Full monthly source files belong to the real production smoke; this fixture validates
    # the same source plan construction, official absence, and local SQL safety predicates.
    plan, before_rows = repair.build_plan(
        database_path, evidence_dir, market_dir, root / exclusions.RECEIPT_DIR / run_id,
    )
    plan["market_validation"] = market_validation
    return plan, before_rows


def _prepare_test_run(
    root: Path, evidence_dir: Path, database_path: Path, monkeypatch: pytest.MonkeyPatch, name: str,
) -> Path:
    market_dir = _write_market_receipt(root, database_path, name)
    market_validation = exclusions._validate_market_chain(
        database_path, root, market_dir.relative_to(root).as_posix(), full_source_validation=False,
    )
    original_validator = exclusions._validate_market_chain
    monkeypatch.setattr(
        exclusions,
        "_validate_market_chain",
        lambda *args, **kwargs: market_validation,
    )
    receipt_dir = root / exclusions.RECEIPT_DIR / name
    result = repair.prepare(database_path, evidence_dir, market_dir, receipt_dir)
    plan, before_rows, _ = repair._load_plan_and_rows(receipt_dir)
    monkeypatch.setattr(
        repair,
        "build_plan",
        lambda *args, **kwargs: ({**plan, "created_at": "2026-09-23T23:00:00+00:00"}, before_rows),
    )
    return receipt_dir


def _row_counts(database_path: Path) -> tuple[int, int]:
    connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    try:
        return tuple(
            connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            for table in ("daily_prices", "technical_indicators")
        )  # type: ignore[return-value]
    finally:
        connection.close()


def test_plan_is_bounded_exact_and_source_backed(evidence_root: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    root, evidence_dir = evidence_root
    database_path = _make_database(root, "plan")
    market_dir = _write_market_receipt(root, database_path, "plan")
    market_validation = exclusions._validate_market_chain(
        database_path, root, market_dir.relative_to(root).as_posix(), full_source_validation=False,
    )
    monkeypatch.setattr(exclusions, "_validate_market_chain", lambda *args, **kwargs: market_validation)
    before_counts = _row_counts(database_path)
    plan, before_rows = repair.build_plan(
        database_path, evidence_dir, market_dir, root / exclusions.RECEIPT_DIR / "plan",
    )
    assert len(plan["keys"]) == 110
    assert len({key[1] for key in plan["keys"] if key[0] == "20260520"}) == 54
    assert plan["closed_dates"] == ["20160211", "20241002", "20250929"]
    assert plan["summary"]["may20_rows_matching_closed_20241002"] == 54
    assert plan["summary"]["may20_rows_also_matching_20171218"] == 50
    assert len(before_rows["tables"]["daily_prices"]) == 110
    assert _row_counts(database_path) == before_counts


def test_apply_and_rollback_recovers_after_commit_before_receipt(
    evidence_root: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, evidence_dir = evidence_root
    database_path = _make_database(root, "recover")
    before_counts = _row_counts(database_path)
    receipt_dir = _prepare_test_run(root, evidence_dir, database_path, monkeypatch, "recover")
    plan_hash = repair.file_hash(receipt_dir / "plan.json")
    applied = repair.apply(receipt_dir / "plan.json", plan_hash, repair.CONFIRM)
    assert applied["state"] == "applied"
    assert _row_counts(database_path) == (before_counts[0] - 110, before_counts[1] - 110)
    real_make_receipt = repair._make_receipt

    def fail_after_rollback_commit(*args: object, **kwargs: object) -> dict[str, object]:
        if len(args) > 3 and args[3] == "rolled_back":
            raise OSError("injected crash after DB commit, before rollback receipt")
        return real_make_receipt(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(repair, "_make_receipt", fail_after_rollback_commit)
    with pytest.raises(OSError, match="injected crash"):
        repair.recover(receipt_dir, rollback=True, confirm=repair.CONFIRM)
    assert _row_counts(database_path) == before_counts
    assert json.loads((receipt_dir / "revision.json").read_text(encoding="utf-8"))["state"] == "applied"

    monkeypatch.setattr(repair, "_make_receipt", real_make_receipt)
    recovered = repair.recover(receipt_dir, rollback=True, confirm=repair.CONFIRM)
    assert recovered["state"] == "rolled_back"
    assert recovered["restored_rows"] == {"daily_prices": 0, "technical_indicators": 0}
    assert _row_counts(database_path) == before_counts
    assert exclusions.load_exclusions(database_path) == set()
    assert exclusions.load_excluded_dates(database_path) == set()


def test_apply_commit_before_receipt_resumes_pending(
    evidence_root: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, evidence_dir = evidence_root
    database_path = _make_database(root, "resume")
    before_counts = _row_counts(database_path)
    receipt_dir = _prepare_test_run(root, evidence_dir, database_path, monkeypatch, "resume")
    original_receipt = repair._make_receipt

    def fail_after_apply_commit(*args: object, **kwargs: object) -> dict[str, object]:
        if len(args) > 3 and args[3] == "applied":
            raise OSError("injected crash after apply commit, before receipt")
        return original_receipt(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(repair, "_make_receipt", fail_after_apply_commit)
    with pytest.raises(OSError, match="apply commit"):
        repair.apply(receipt_dir / "plan.json", repair.file_hash(receipt_dir / "plan.json"), repair.CONFIRM)
    assert _row_counts(database_path) == (before_counts[0] - 110, before_counts[1] - 110)
    with pytest.raises(ValueError, match="進行中"):
        exclusions.load_exclusions(database_path)
    monkeypatch.setattr(repair, "_make_receipt", original_receipt)
    recovered = repair.recover(receipt_dir, rollback=False, confirm=repair.CONFIRM)
    assert recovered["state"] == "applied"
    assert len(exclusions.load_exclusions(database_path)) == 110


def test_applied_exclusions_close_dates_and_pit_prefix(
    evidence_root: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, evidence_dir = evidence_root
    database_path = _make_database(root, "pit")
    receipt_dir = _prepare_test_run(root, evidence_dir, database_path, monkeypatch, "pit")
    plan_hash = repair.file_hash(receipt_dir / "plan.json")
    repair.apply(receipt_dir / "plan.json", plan_hash, repair.CONFIRM)

    exact = exclusions.load_exclusions(database_path)
    dates = exclusions.load_excluded_dates(database_path)
    assert len(exact) == 110
    assert dates == {"20160211", "20241002", "20250929"}
    evidence = exclusions.load_exclusion_evidence(database_path)
    assert len(evidence) == 1
    assert len(evidence[0]["keys"]) == 110
    assert evidence[0]["acquired_at"].startswith("2026-09-23T22:")
    with pytest.raises(ValueError, match="已核驗排除列"):
        exclusions.validate_excluded_daily_price_rows(
            database_path, [{"日期": "20250929", "證券代號": "9999"}],
        )
    with pytest.raises(ValueError, match="已核驗排除列"):
        exclusions.validate_excluded_daily_price_rows(
            database_path, [{"日期": "20260520", "證券代號": MISSING_SYMBOLS[0]}],
        )
    exclusions.validate_excluded_daily_price_rows(
        database_path, [{"日期": "20260521", "證券代號": MISSING_SYMBOLS[0]}],
    )
    exclusions.assert_excluded_source_revision_safe(database_path, date(2016, 2, 10))
    with pytest.raises(ValueError, match="blocks historical PIT"):
        exclusions.assert_excluded_source_revision_safe(database_path, date(2016, 2, 11))

    from data_module import formal_market_revision, historical_session_revision
    from data_module.ml_daily_price_revision_gate import (
        DailyPriceSourceRevisionError,
        check_daily_price_source_revision,
    )

    monkeypatch.setattr(formal_market_revision, "assert_market_revision_safe", lambda *_: None)
    monkeypatch.setattr(historical_session_revision, "assert_session_revision_safe", lambda *_: None)
    with pytest.raises(DailyPriceSourceRevisionError, match="blocks historical PIT"):
        check_daily_price_source_revision(
            database_path=database_path,
            decision_date=date(2016, 2, 11),
            symbols=["2330"],
        )


def test_rollback_rejects_later_rows_drift(
    evidence_root: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, evidence_dir = evidence_root
    database_path = _make_database(root, "drift")
    receipt_dir = _prepare_test_run(root, evidence_dir, database_path, monkeypatch, "drift")
    repair.apply(receipt_dir / "plan.json", repair.file_hash(receipt_dir / "plan.json"), repair.CONFIRM)
    connection = sqlite3.connect(database_path)
    connection.execute(
        'INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)',
        ("20160211", "LATER", 5, 1, 1, 1, 1),
    )
    connection.commit()
    connection.close()
    with pytest.raises(ValueError, match="漂移|仍有列"):
        repair.recover(receipt_dir, rollback=True, confirm=repair.CONFIRM)
    connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    try:
        assert connection.execute(
            'SELECT count(*) FROM daily_prices WHERE "日期"=? AND "證券代號"=?',
            ("20160211", "LATER"),
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_pending_marker_fails_closed_and_source_tamper_is_detected(
    evidence_root: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, evidence_dir = evidence_root
    database_path = _make_database(root, "pending")
    receipt_dir = _prepare_test_run(root, evidence_dir, database_path, monkeypatch, "pending")
    repair.apply(receipt_dir / "plan.json", repair.file_hash(receipt_dir / "plan.json"), repair.CONFIRM)
    payload = evidence_dir / "twse-20260520.json"
    before = payload.read_bytes()
    payload.write_bytes(before + b" ")
    with pytest.raises(ValueError, match="hash|receipt"):
        exclusions.load_exclusions(database_path)
    payload.write_bytes(before)
    revision_path = receipt_dir / "revision.json"
    marker = json.loads(revision_path.read_text(encoding="utf-8"))
    marker["state"] = "pending"
    _write_json(revision_path, marker)
    with pytest.raises(ValueError, match="進行中"):
        exclusions.load_exclusions(database_path)
