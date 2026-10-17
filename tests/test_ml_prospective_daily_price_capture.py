from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3

import pytest

from data_module.formal_market_revision import (
    RECEIPT_DIR,
    collect_market_revision_evidence,
    inspect_market_revision_state,
)
from data_module.ml_prospective_daily_price_capture import (
    MAX_SOURCE_RESPONSE_BYTES,
    ProspectiveDailyPriceCaptureError,
    capture_prospective_daily_price_candidate,
)
from data_module.official_daily_price_custody import persist_official_daily_price_response
from data_module.tpex_daily_price_backfill import normalize_tpex_daily_price_rows
from data_module.tpex_daily_price_source import _rows_from_after_trading_response


SOURCE_DATE = "2026-09-30"
_TWSE_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
_TPEX_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc"


def _database(tmp_path: Path) -> tuple[Path, Path]:
    data_root = tmp_path / "data"
    sqlite_dir = data_root / "sqlite"
    sqlite_dir.mkdir(parents=True)
    database = sqlite_dir / "twstock.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE identity_fixture (id INTEGER PRIMARY KEY)")
    return data_root, database


def _write_revision(
    database: Path,
    *,
    state: str = "applied",
    run_id: str = "revision-run",
    database_identity: Path | None = None,
    end_date: str = "2026-09-23",
) -> Path:
    data_root = database.parent.parent
    run_dir = data_root / RECEIPT_DIR / run_id
    run_dir.mkdir(parents=True)
    identity = str((database_identity or database).resolve())
    plan = {
        "schema_version": "formal-market-repair.v1",
        "database_path": identity,
        "source_start_date": "2014-01-02",
        "source_end_date": end_date,
    }
    plan_bytes = json.dumps(plan, sort_keys=True).encode("utf-8")
    plan_hash = hashlib.sha256(plan_bytes).hexdigest()
    journal_bytes = json.dumps(
        {"schema_version": "formal-market-repair.v1", "plan_sha256": plan_hash},
        sort_keys=True,
    ).encode("utf-8")
    marker: dict[str, object] = {
        "schema_version": "formal-market-revision.v1",
        "database_path": identity,
        "source_start_date": plan["source_start_date"],
        "source_end_date": plan["source_end_date"],
        "state": state,
    }
    (run_dir / "plan.json").write_bytes(plan_bytes)
    (run_dir / "journal.json").write_bytes(journal_bytes)
    if state == "applied":
        receipt_bytes = json.dumps(
            {"schema_version": "formal-market-repair.v1", "plan_sha256": plan_hash},
            sort_keys=True,
        ).encode("utf-8")
        (run_dir / "receipt.json").write_bytes(receipt_bytes)
        marker["receipt_sha256"] = hashlib.sha256(receipt_bytes).hexdigest()
    elif state == "rolled_back":
        rollback_bytes = b"rollback-evidence"
        (run_dir / "rollback.json").write_bytes(rollback_bytes)
        marker["rollback_sha256"] = hashlib.sha256(rollback_bytes).hexdigest()
    (run_dir / "revision.json").write_text(
        json.dumps(marker, sort_keys=True), encoding="utf-8"
    )
    return run_dir


def _twse_payload(*, response_date: str = "20260930") -> dict[str, object]:
    fields = ["證券代號", "證券名稱", "收盤價"]
    return {
        "stat": "OK",
        "date": response_date,
        "tables": [
            {
                "fields": fields,
                "data": [["2330", "台積電", "1,000"]],
            }
        ],
    }


def _tpex_payload(*, response_date: str = "115/09/30") -> dict[str, object]:
    return {
        "tables": [
            {
                "date": response_date,
                "fields": ["代號", "名稱", "收盤"],
                "data": [["6488", "環球晶", "500"]],
            }
        ]
    }


def _write_source(
    source_root: Path,
    venue: str,
    *,
    source_date: str = SOURCE_DATE,
    payload: dict[str, object] | None = None,
    captured_at: datetime | None = None,
    source_id: str | None = None,
    parser_override: str | None = None,
) -> tuple[Path, Path]:
    observed = captured_at or datetime.now(timezone.utc) - timedelta(minutes=5)
    if venue == "twse":
        body = payload or _twse_payload()
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        columns = body["tables"][0]["fields"]  # type: ignore[index]
        requested_url = final_url = _TWSE_URL
        parameters = {
            "date": source_date.replace("-", ""),
            "type": "ALL",
            "response": "json",
        }
        default_source_id = "twse.mi_index.daily_price"
        parser_id = "twse.mi_index.v1"
    elif venue == "tpex":
        body = payload or _tpex_payload()
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        raw_rows = _rows_from_after_trading_response(
            body,
            fallback_date=source_date.replace("-", ""),
        )
        normalized = normalize_tpex_daily_price_rows(
            raw_rows,
            fallback_date=source_date.replace("-", ""),
            strict=False,
        )
        columns = list(normalized.rows[0].keys())
        requested_url = final_url = _TPEX_URL
        parameters = {
            "date": f"{source_date[:4]}/{source_date[5:7]}/{source_date[8:10]}",
            "type": "EW",
            "response": "json",
        }
        default_source_id = "tpex.daily_close_quotes"
        parser_id = "tpex.daily_close_quotes.v1"
    else:
        raise AssertionError(venue)
    result = persist_official_daily_price_response(
        output_root=source_root,
        venue=venue,
        source_id=source_id or default_source_id,
        source_date=source_date,
        requested_url=requested_url,
        final_url=final_url,
        request_parameters=parameters,
        http_status=200,
        response_headers={"content-type": "application/json"},
        raw_response=raw,
        captured_at=observed,
        row_count=1,
        source_columns=columns,
        parser_id=parser_override or parser_id,
        historical_backfill_claimed=False,
    )
    return Path(str(result["receipt_path"])), Path(str(result["raw_response_path"]))


def _capture(
    tmp_path: Path,
    *,
    only_venues: tuple[str, ...] = ("twse", "tpex"),
    source_kwargs: dict[str, dict[str, object]] | None = None,
    revision_state: str = "applied",
) -> tuple[Path, Path, Path, list[tuple[Path, Path]]]:
    data_root, database = _database(tmp_path)
    _write_revision(database, state=revision_state)
    source_root = tmp_path / "source-output"
    source_root.mkdir()
    pairs: list[tuple[Path, Path]] = []
    for venue in only_venues:
        options = dict((source_kwargs or {}).get(venue, {}))
        pairs.append(_write_source(source_root, venue, **options))
    candidate_root = tmp_path / "repo-candidates"
    return data_root, database, source_root, pairs


def _run_capture(
    tmp_path: Path,
    *,
    candidate_root: Path | None = None,
    preview_only: bool = True,
    only_venues: tuple[str, ...] = ("twse", "tpex"),
    source_kwargs: dict[str, dict[str, object]] | None = None,
    revision_state: str = "applied",
) -> tuple[dict[str, object], Path, Path, Path, list[tuple[Path, Path]]]:
    data_root, database, source_root, pairs = _capture(
        tmp_path,
        only_venues=only_venues,
        source_kwargs=source_kwargs,
        revision_state=revision_state,
    )
    output_root = candidate_root or tmp_path / "repo-candidates"
    result = capture_prospective_daily_price_candidate(
        source_output_root=source_root,
        database_path=database,
        source_date=SOURCE_DATE,
        candidate_root=output_root,
        preview_only=preview_only,
    )
    return result, data_root, database, source_root, pairs


def test_inspector_is_cutoff_free_but_legacy_guard_keeps_temporal_hold(tmp_path: Path) -> None:
    _, database = _database(tmp_path)
    run_dir = _write_revision(database)

    inspected = inspect_market_revision_state(database)

    assert inspected.database_path == str(database.resolve())
    assert inspected.runs[0].state == "applied"
    assert inspected.runs[0].source_start_date == "2014-01-02"
    assert inspected.runs[0].source_end_date == "2026-09-23"
    assert any(item.role_id.endswith("/receipt.json") for item in inspected.evidence.files)
    with pytest.raises(ValueError, match="historical PIT"):
        collect_market_revision_evidence(database, date(2026, 9, 30))
    assert (run_dir / "receipt.json").is_file()


def test_inspector_keeps_rolled_back_evidence_and_rejects_pending_or_bad_chain(
    tmp_path: Path,
) -> None:
    _, rolled_database = _database(tmp_path / "rolled")
    _write_revision(rolled_database, state="rolled_back")
    rolled = inspect_market_revision_state(rolled_database)
    assert rolled.runs[0].state == "rolled_back"
    assert any(item.role_id.endswith("/rollback.json") for item in rolled.evidence.files)

    _, pending_database = _database(tmp_path / "pending")
    _write_revision(pending_database, state="pending")
    pending = inspect_market_revision_state(pending_database)
    assert pending.runs[0].state == "pending"
    with pytest.raises(ProspectiveDailyPriceCaptureError, match="pending run"):
        _run_capture(tmp_path / "pending-candidate", revision_state="pending")

    _, bad_database = _database(tmp_path / "bad")
    run_dir = _write_revision(bad_database)
    (run_dir / "plan.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="無法驗證"):
        inspect_market_revision_state(bad_database)


def test_inspector_rejects_database_mismatch_and_invalid_range(tmp_path: Path) -> None:
    _, database = _database(tmp_path)
    _, other_database = _database(tmp_path / "other")
    _write_revision(database, database_identity=other_database)
    with pytest.raises(ValueError, match="無法驗證"):
        inspect_market_revision_state(database)

    _, invalid_database = _database(tmp_path / "invalid-range")
    _write_revision(invalid_database, end_date="2013-12-31")
    with pytest.raises(ValueError, match="無法驗證"):
        inspect_market_revision_state(invalid_database)


def test_preview_and_capture_copy_exact_bytes_with_nonformal_claims(tmp_path: Path) -> None:
    preview, _, database, source_root, pairs = _run_capture(tmp_path / "preview")
    assert preview["status"] == "preview_only"
    assert not (tmp_path / "preview" / "repo-candidates").exists()
    assert preview["historical_pit_eligible"] is False
    assert preview["formal_oos_allowed"] is False
    assert preview["formal_credit"] is False
    assert preview["features_included"] is False
    assert preview["labels_included"] is False
    assert preview["model_use_claimed"] is False
    assert preview["market_revision"]["cutoff_policy_evaluated"] is False  # type: ignore[index]
    assert preview["source_date"] == SOURCE_DATE
    assert all(
        source["available_at"] <= preview["observation_cutoff_at"]  # type: ignore[index]
        for source in preview["sources"]  # type: ignore[index]
    )
    assert database.is_file() and source_root.is_dir()

    _, capture_database, capture_source_root, source_pairs = _capture(
        tmp_path / "capture",
    )
    database_hash_before = hashlib.sha256(capture_database.read_bytes()).hexdigest()
    captured = capture_prospective_daily_price_candidate(
        source_output_root=capture_source_root,
        database_path=capture_database,
        source_date=SOURCE_DATE,
        candidate_root=tmp_path / "capture" / "repo-candidates",
        preview_only=False,
    )
    assert captured["status"] == "captured"
    assert captured["candidate_readback_verified"] is True
    assert captured["candidate_available_at"] >= captured["candidate_observed_at"]
    assert captured["historical_pit_eligible"] is False
    assert captured["formal_credit"] is False
    assert captured["features_included"] is False
    assert captured["labels_included"] is False
    assert captured["model_use_claimed"] is False
    assert hashlib.sha256(capture_database.read_bytes()).hexdigest() == database_hash_before
    candidate_dir = Path(str(captured["candidate_directory"]))
    for receipt_path, raw_path in source_pairs:
        venue = json.loads(receipt_path.read_text(encoding="utf-8"))["source_authority"]
        candidate_raw = candidate_dir / "sources" / venue / "raw_response.bin"
        candidate_receipt = candidate_dir / "sources" / venue / "source_receipt.json"
        assert candidate_raw.read_bytes() == raw_path.read_bytes()
        assert candidate_receipt.read_bytes() == receipt_path.read_bytes()
    names = sorted(path.name for path in candidate_dir.rglob("*"))
    again = capture_prospective_daily_price_candidate(
        source_output_root=capture_source_root,
        database_path=capture_database,
        source_date=SOURCE_DATE,
        candidate_root=tmp_path / "capture" / "repo-candidates",
        preview_only=False,
    )
    assert again["status"] == "already_captured"
    assert again["candidate_available_at"] == captured["candidate_available_at"]
    assert sorted(path.name for path in candidate_dir.rglob("*")) == names


@pytest.mark.parametrize("parser_id", ["twse.mi_index.v1", "twse.mi_index.direction_text.v2"])
def test_prospective_capture_preserves_exact_supported_twse_parser(tmp_path: Path, parser_id: str) -> None:
    captured, _, _, _, pairs = _run_capture(
        tmp_path, preview_only=False, source_kwargs={"twse": {"parser_override": parser_id}},
    )
    assert captured["status"] == "captured" and captured["historical_pit_eligible"] is False
    source = next(item for item in captured["sources"] if item["venue"] == "twse")
    assert source["parser_id"] == parser_id
    candidate = Path(str(captured["candidate_directory"])) / "sources/twse/source_receipt.json"
    assert candidate.read_bytes() == pairs[0][0].read_bytes()


def test_prospective_capture_rejects_unrecognized_twse_parser(tmp_path: Path) -> None:
    with pytest.raises(ProspectiveDailyPriceCaptureError, match="identity mismatch"):
        _run_capture(tmp_path, source_kwargs={"twse": {"parser_override": "twse.mi_index.fake.v9"}})


def test_candidate_root_cannot_be_ancestor_of_protected_roots(tmp_path: Path) -> None:
    _, database, source_root, _ = _capture(tmp_path)

    with pytest.raises(ProspectiveDailyPriceCaptureError, match="must be isolated"):
        capture_prospective_daily_price_candidate(
            source_output_root=source_root,
            database_path=database,
            source_date=SOURCE_DATE,
            candidate_root=tmp_path,
            preview_only=True,
        )


def test_missing_venue_and_crossvenue_source_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ProspectiveDailyPriceCaptureError, match="missing: tpex"):
        _run_capture(tmp_path / "missing", only_venues=("twse",))

    data_root, database, source_root, _ = _capture(
        tmp_path / "cross",
        source_kwargs={"tpex": {"source_id": "twse.mi_index.daily_price"}},
    )
    with pytest.raises(ProspectiveDailyPriceCaptureError, match="identity mismatch"):
        capture_prospective_daily_price_candidate(
            source_output_root=source_root,
            database_path=database,
            source_date=SOURCE_DATE,
            candidate_root=tmp_path / "cross-candidates",
            preview_only=True,
        )


def test_response_date_and_actual_row_count_are_validated(tmp_path: Path) -> None:
    wrong_date = _twse_payload(response_date="20260929")
    with pytest.raises(ProspectiveDailyPriceCaptureError, match="response date"):
        _run_capture(
            tmp_path / "date",
            source_kwargs={"twse": {"payload": wrong_date}},
        )

    wrong_tpex_date = _tpex_payload(response_date="115/09/29")
    with pytest.raises(ProspectiveDailyPriceCaptureError, match="TPEx response date"):
        _run_capture(
            tmp_path / "tpex-date",
            source_kwargs={"tpex": {"payload": wrong_tpex_date}},
        )

    data_root, database, source_root, pairs = _capture(tmp_path / "rowcount")
    receipt_path, _ = pairs[0]
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["row_count"] = 2
    body = {key: value for key, value in payload.items() if key != "content_sha256"}
    payload["content_sha256"] = "sha256:" + hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    receipt_path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    with pytest.raises(ProspectiveDailyPriceCaptureError, match="row count"):
        capture_prospective_daily_price_candidate(
            source_output_root=source_root,
            database_path=database,
            source_date=SOURCE_DATE,
            candidate_root=tmp_path / "rowcount-candidates",
            preview_only=True,
        )


def test_raw_receipt_tamper_and_future_availability_fail_closed(tmp_path: Path) -> None:
    _, database, source_root, pairs = _capture(tmp_path / "tamper-raw")
    raw_path = pairs[0][1]
    raw_path.write_bytes(raw_path.read_bytes() + b" ")
    with pytest.raises(ProspectiveDailyPriceCaptureError, match="hash/size mismatch"):
        capture_prospective_daily_price_candidate(
            source_output_root=source_root,
            database_path=database,
            source_date=SOURCE_DATE,
            candidate_root=tmp_path / "tamper-raw-candidates",
            preview_only=True,
        )

    _, database2, source_root2, pairs2 = _capture(tmp_path / "tamper-receipt")
    receipt_path = pairs2[0][0]
    receipt_value = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt_value["content_sha256"] = "sha256:" + ("0" * 64)
    receipt_path.write_text(
        json.dumps(receipt_value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ProspectiveDailyPriceCaptureError, match="content hash mismatch"):
        capture_prospective_daily_price_candidate(
            source_output_root=source_root2,
            database_path=database2,
            source_date=SOURCE_DATE,
            candidate_root=tmp_path / "tamper-receipt-candidates",
            preview_only=True,
        )

    future = datetime.now(timezone.utc) + timedelta(minutes=1)
    _, database3, source_root3, _ = _capture(
        tmp_path / "future",
        source_kwargs={"tpex": {"captured_at": future}},
    )
    with pytest.raises(ProspectiveDailyPriceCaptureError, match="after observed_at"):
        capture_prospective_daily_price_candidate(
            source_output_root=source_root3,
            database_path=database3,
            source_date=SOURCE_DATE,
            candidate_root=tmp_path / "future-candidates",
            preview_only=True,
        )


def test_oversized_raw_is_rejected_before_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, database, source_root, pairs = _capture(tmp_path / "oversized")
    raw_path = pairs[0][1]
    with raw_path.open("wb") as stream:
        stream.truncate(MAX_SOURCE_RESPONSE_BYTES + 1)
    original_open = Path.open

    def reject_oversized_open(path: Path, *args: object, **kwargs: object):
        if path.resolve() == raw_path.resolve():
            raise AssertionError("oversized source raw file must be rejected before read")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", reject_oversized_open)
    with pytest.raises(ProspectiveDailyPriceCaptureError, match="bounded single-link"):
        capture_prospective_daily_price_candidate(
            source_output_root=source_root,
            database_path=database,
            source_date=SOURCE_DATE,
            candidate_root=tmp_path / "oversized-candidates",
            preview_only=True,
        )


def test_hardlinked_source_response_is_rejected(tmp_path: Path) -> None:
    _, database, source_root, pairs = _capture(tmp_path / "hardlink")
    raw_path = pairs[0][1]
    hardlink = raw_path.with_name("linked-raw-response.bin")
    os.link(raw_path, hardlink)
    with pytest.raises(ProspectiveDailyPriceCaptureError, match="single-link regular file"):
        capture_prospective_daily_price_candidate(
            source_output_root=source_root,
            database_path=database,
            source_date=SOURCE_DATE,
            candidate_root=tmp_path / "hardlink-candidates",
            preview_only=True,
        )


def test_candidate_retry_is_create_only_and_tamper_is_conflict(tmp_path: Path) -> None:
    _, database, source_root, pairs = _capture(tmp_path / "retry")
    candidate_root = tmp_path / "repo-candidates"
    arguments = {
        "source_output_root": source_root,
        "database_path": database,
        "source_date": SOURCE_DATE,
        "candidate_root": candidate_root,
        "preview_only": False,
    }
    first = capture_prospective_daily_price_candidate(**arguments)
    assert first["status"] == "captured"
    candidate_dir = Path(str(first["candidate_directory"]))
    before = sorted(str(path.relative_to(candidate_dir)) for path in candidate_dir.rglob("*"))
    second = capture_prospective_daily_price_candidate(**arguments)
    after = sorted(str(path.relative_to(candidate_dir)) for path in candidate_dir.rglob("*"))
    assert second["status"] == "already_captured"
    assert second["candidate_available_at"] == first["candidate_available_at"]
    assert before == after

    raw_copy = candidate_dir / "sources" / "twse" / "raw_response.bin"
    raw_copy.write_bytes(raw_copy.read_bytes() + b" ")
    with pytest.raises(ProspectiveDailyPriceCaptureError, match="immutable candidate conflict"):
        capture_prospective_daily_price_candidate(**arguments)
