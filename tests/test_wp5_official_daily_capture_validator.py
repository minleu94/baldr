from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path

import pytest

from data_module.wp5_official_daily_capture_validator import (
    CAPTURE_DIRECTORY_NAME,
    DEFAULT_DECISION_DATE,
    OUTPUT_SCHEMA,
    TPEX_FIELDS,
    TWSE_FIELDS,
    CaptureValidationError,
    validate_official_daily_capture,
)


CAPTURE_START = "2026-09-29T15:18:27.1665879+00:00"
TWSE_END = "2026-09-29T15:18:27.8257766+00:00"
TPEX_START = "2026-09-29T15:18:27.8800087+00:00"
TPEX_END = "2026-09-29T15:18:31.0739265+00:00"
CAPTURE_FINISHED = "2026-09-29T15:18:31.1063917+00:00"
TEST_CUTOFF = datetime.fromisoformat("2026-09-29T15:30:00+00:00")


def _twse_row(code: str, shares: str, close: str = "2475.00") -> list[str]:
    return [
        code, "測試證券", shares, "1", "100000", "2470.00", "2480.00",
        "2460.00", close, "", "0.00", "2470.00", "1", "2480.00", "1", "10.00",
    ]


def _tpex_row(code: str, shares: str, close: str = "125.50") -> list[str]:
    return [
        code, "測試上櫃", close, "0.50", "125.00", "126.00", "124.50", "125.20",
        shares, "100000", "10", "125.00", "1", "125.50", "1", "1000000",
        "125.50", "138.00", "113.00",
    ]


def _base_payloads() -> tuple[dict, dict]:
    twse = {
        "date": "20260929",
        "stat": "OK",
        "type": "ALL",
        "tables": [{"fields": [], "data": []} for _ in range(8)] + [
            {"fields": list(TWSE_FIELDS), "data": [
                _twse_row("2330", "26,893,348"),
                _twse_row("2317", "12,000"),
            ]}
        ],
    }
    tpex = {
        "date": "20260929",
        "stat": "ok",
        "tables": [
            {
                "fields": list(TPEX_FIELDS),
                "data": [
                    _tpex_row("6488", "9,157,413"),
                    _tpex_row("5347", "1,234"),
                ],
                "totalCount": 2,
            },
            {"fields": list(TPEX_FIELDS), "data": [], "totalCount": 0},
        ],
    }
    return twse, tpex


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _build_capture(
    repo_root: Path,
    *,
    decision_date: date = DEFAULT_DECISION_DATE,
    mutate: object | None = None,
) -> tuple[Path, str, str]:
    capture_dir = repo_root / "output" / "qa" / CAPTURE_DIRECTORY_NAME
    capture_dir.mkdir(parents=True)
    twse, tpex = _base_payloads()
    date_compact = decision_date.strftime("%Y%m%d")
    date_slash = (
        f"{decision_date.year:04d}%2F{decision_date.month:02d}"
        f"%2F{decision_date.day:02d}"
    )
    twse["date"] = date_compact
    tpex["date"] = date_compact
    if mutate is not None:
        mutate(twse, tpex)  # type: ignore[operator]
    date_prefix = decision_date.isoformat()
    run_id = f"{date_compact}T151827Z_fixture"
    capture_start = f"{date_prefix}T15:18:27.1665879+00:00"
    twse_end = f"{date_prefix}T15:18:27.8257766+00:00"
    tpex_start = f"{date_prefix}T15:18:27.8800087+00:00"
    tpex_end = f"{date_prefix}T15:18:31.0739265+00:00"
    capture_finished = f"{date_prefix}T15:18:31.1063917+00:00"

    captures = []
    raw_files = []
    for name, filename, url, payload, start, end in (
        (
            "twse_mi_index", f"twse_mi_index_{date_compact}.json",
            f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={date_compact}&type=ALL&response=json",
            twse, capture_start, twse_end,
        ),
        (
            "tpex_daily_quotes", f"tpex_daily_quotes_{date_compact}.json",
            f"https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date={date_slash}&id=&response=json",
            tpex, tpex_start, tpex_end,
        ),
    ):
        raw = _json_bytes(payload)
        (capture_dir / filename).write_bytes(raw)
        digest = _sha(raw)
        captures.append(
            {
                "name": name,
                "request_url": url,
                "final_url": url,
                "capture_start_utc": start,
                "capture_end_utc": end,
                "http_status": 200,
                "content_type": "application/json; charset=UTF-8",
                "body_file": filename,
                "body_bytes": len(raw),
                "body_sha256": digest,
                "readback_bytes": len(raw),
                "readback_sha256": digest,
                "readback_verified": True,
                "result": "captured_verified",
            }
        )
        raw_files.append(
            {
                "name": name,
                "file": filename,
                "http_status": 200,
                "bytes": len(raw),
                "sha256": digest,
                "readback_bytes": len(raw),
                "readback_sha256": digest,
                "readback_verified": True,
            }
        )

    receipt = {
        "schema_version": 1,
        "run_id": run_id,
        "run_status": "success_raw_capture_readback_verified",
        "capture_directory": str(capture_dir.resolve()),
        "started_at_utc": capture_start,
        "finished_at_utc": capture_finished,
        "formal_pit": False,
        "captures": captures,
    }
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "run_status": "success_raw_capture_readback_verified",
        "capture_directory": str(capture_dir.resolve()),
        "receipt_file": "capture_receipt.json",
        "raw_files": raw_files,
    }
    (capture_dir / "capture_receipt.json").write_bytes(_json_bytes(receipt))
    (capture_dir / "capture_manifest.json").write_bytes(_json_bytes(manifest))
    receipt_sha = _sha((capture_dir / "capture_receipt.json").read_bytes())
    manifest_sha = _sha((capture_dir / "capture_manifest.json").read_bytes())
    return capture_dir, receipt_sha, manifest_sha


def _validate(
    repo_root: Path,
    capture_dir: Path,
    receipt_sha: str,
    manifest_sha: str,
    *,
    decision_date: date = DEFAULT_DECISION_DATE,
    required_symbols_by_venue: dict[str, str] | None = None,
    cutoff: datetime = TEST_CUTOFF,
) -> dict:
    return validate_official_daily_capture(
        capture_dir,
        expected_receipt_sha256=receipt_sha,
        expected_manifest_sha256=manifest_sha,
        decision_date=decision_date,
        required_symbols_by_venue=required_symbols_by_venue or {
            "TWSE": "2330", "TPEx": "6488"
        },
        cutoff_utc=cutoff,
        repo_root=repo_root,
    )


def test_valid_capture_reports_only_same_day_activity_without_pit_or_closure_claim(
    tmp_path: Path,
) -> None:
    capture_dir, receipt_sha, manifest_sha = _build_capture(tmp_path)
    before = sorted(path.name for path in capture_dir.iterdir())

    result = _validate(tmp_path, capture_dir, receipt_sha, manifest_sha)

    assert result["schema_version"] == OUTPUT_SCHEMA
    assert result["status"] == "validated"
    assert result["evidence_kind"] == "official_same_day_market_activity_observed"
    assert result["cutoff_utc"] == "2026-09-29T15:30:00Z"
    assert result["markets"]["twse_mi_index"]["rows"] == 2
    assert result["markets"]["twse_mi_index"]["required_symbol_volume_shares"] == 26893348
    assert len(result["markets"]["twse_mi_index"]["raw_sha256"]) == 64
    assert result["markets"]["twse_mi_index"]["raw_bytes"] > 0
    assert result["markets"]["tpex_daily_quotes"]["rows"] == 2
    assert result["markets"]["tpex_daily_quotes"]["total_count"] == 2
    assert result["markets"]["tpex_daily_quotes"]["required_symbol_volume_shares"] == 9157413
    assert len(result["markets"]["tpex_daily_quotes"]["raw_sha256"]) == 64
    assert result["markets"]["tpex_daily_quotes"]["raw_bytes"] > 0
    assert result["available_at_utc"] == TPEX_END
    assert result["official_published_at_utc"] == "unknown"
    assert result["temporary_closure_negative_coverage"] is False
    assert result["closure_gate_passed"] is False
    assert result["formal_pit"] is False
    assert sorted(path.name for path in capture_dir.iterdir()) == before


@pytest.mark.parametrize(
    ("pin_name", "expected_code"),
    [
        ("receipt", "receipt_sha256_mismatch"),
        ("manifest", "manifest_sha256_mismatch"),
    ],
)
def test_caller_hash_pins_are_required(
    tmp_path: Path, pin_name: str, expected_code: str
) -> None:
    capture_dir, receipt_sha, manifest_sha = _build_capture(tmp_path)
    if pin_name == "receipt":
        receipt_sha = "0" * 64
    else:
        manifest_sha = "0" * 64

    with pytest.raises(CaptureValidationError) as error:
        _validate(tmp_path, capture_dir, receipt_sha, manifest_sha)

    assert error.value.code == expected_code


def test_content_type_rejects_jsonp_even_with_json_prefix(tmp_path: Path) -> None:
    capture_dir, _receipt_sha, manifest_sha = _build_capture(tmp_path)
    receipt_path = capture_dir / "capture_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["captures"][0]["content_type"] = "application/jsonp"
    receipt_bytes = _json_bytes(receipt)
    receipt_path.write_bytes(receipt_bytes)

    with pytest.raises(CaptureValidationError) as error:
        _validate(tmp_path, capture_dir, _sha(receipt_bytes), manifest_sha)

    assert error.value.code == "twse_mi_index_content_type_invalid"


@pytest.mark.parametrize("metadata_file", ["receipt", "manifest"])
def test_untrusted_published_at_claim_is_rejected_even_with_updated_pin(
    tmp_path: Path,
    metadata_file: str,
) -> None:
    capture_dir, receipt_sha, manifest_sha = _build_capture(tmp_path)
    if metadata_file == "receipt":
        metadata_path = capture_dir / "capture_receipt.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    else:
        metadata_path = capture_dir / "capture_manifest.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["official_published_at_utc"] = "2026-09-29T15:00:00Z"
    metadata_bytes = _json_bytes(metadata)
    metadata_path.write_bytes(metadata_bytes)
    if metadata_file == "receipt":
        receipt_sha = _sha(metadata_bytes)
    else:
        manifest_sha = _sha(metadata_bytes)

    with pytest.raises(CaptureValidationError) as error:
        _validate(tmp_path, capture_dir, receipt_sha, manifest_sha)

    assert error.value.code == "capture_publication_time_claim_rejected"


@pytest.mark.parametrize("truncate", [False, True], ids=["hash-change", "truncated"])
def test_changed_or_truncated_raw_bytes_fail_readback(
    tmp_path: Path, truncate: bool
) -> None:
    capture_dir, receipt_sha, manifest_sha = _build_capture(tmp_path)
    raw_path = capture_dir / "twse_mi_index_20260929.json"
    raw = raw_path.read_bytes()
    raw_path.write_bytes(raw[:-1] if truncate else raw + b" ")

    with pytest.raises(CaptureValidationError) as error:
        _validate(tmp_path, capture_dir, receipt_sha, manifest_sha)

    assert error.value.code == "twse_mi_index_raw_readback_mismatch"


def test_wrong_market_date_fails_closed(tmp_path: Path) -> None:
    def mutate(_twse: dict, tpex: dict) -> None:
        tpex["date"] = "20260928"

    capture_dir, receipt_sha, manifest_sha = _build_capture(tmp_path, mutate=mutate)
    with pytest.raises(CaptureValidationError) as error:
        _validate(tmp_path, capture_dir, receipt_sha, manifest_sha)
    assert error.value.code == "tpex_date_mismatch"


def test_empty_daily_table_fails_closed(tmp_path: Path) -> None:
    def mutate(twse: dict, _tpex: dict) -> None:
        twse["tables"][8]["data"] = []

    capture_dir, receipt_sha, manifest_sha = _build_capture(tmp_path, mutate=mutate)
    with pytest.raises(CaptureValidationError) as error:
        _validate(tmp_path, capture_dir, receipt_sha, manifest_sha)
    assert error.value.code == "twse_mi_index_empty_rows"


def test_duplicate_market_code_fails_closed(tmp_path: Path) -> None:
    def mutate(_twse: dict, tpex: dict) -> None:
        tpex["tables"][0]["data"].append(list(tpex["tables"][0]["data"][0]))
        tpex["tables"][0]["totalCount"] += 1

    capture_dir, receipt_sha, manifest_sha = _build_capture(tmp_path, mutate=mutate)
    with pytest.raises(CaptureValidationError) as error:
        _validate(tmp_path, capture_dir, receipt_sha, manifest_sha)
    assert error.value.code == "tpex_daily_quotes_duplicate_symbol"


def test_required_twse_symbol_must_be_present_and_trading(tmp_path: Path) -> None:
    def mutate(twse: dict, _tpex: dict) -> None:
        twse["tables"][8]["data"] = [twse["tables"][8]["data"][1]]

    capture_dir, receipt_sha, manifest_sha = _build_capture(tmp_path, mutate=mutate)
    with pytest.raises(CaptureValidationError) as error:
        _validate(tmp_path, capture_dir, receipt_sha, manifest_sha)
    assert error.value.code == "twse_mi_index_required_symbol_missing"


def test_required_tpex_symbol_requires_positive_volume(tmp_path: Path) -> None:
    def mutate(_twse: dict, tpex: dict) -> None:
        tpex["tables"][0]["data"][0][8] = "0"

    capture_dir, receipt_sha, manifest_sha = _build_capture(tmp_path, mutate=mutate)
    with pytest.raises(CaptureValidationError) as error:
        _validate(tmp_path, capture_dir, receipt_sha, manifest_sha)
    assert error.value.code == "tpex_daily_quotes_required_symbol_no_positive_volume"


def test_tpex_total_count_must_match_rows(tmp_path: Path) -> None:
    def mutate(_twse: dict, tpex: dict) -> None:
        tpex["tables"][0]["totalCount"] = 3

    capture_dir, receipt_sha, manifest_sha = _build_capture(tmp_path, mutate=mutate)
    with pytest.raises(CaptureValidationError) as error:
        _validate(tmp_path, capture_dir, receipt_sha, manifest_sha)
    assert error.value.code == "tpex_total_count_mismatch"


def test_validator_accepts_another_caller_pinned_date_fixture(tmp_path: Path) -> None:
    other_date = date(2026, 9, 28)
    capture_dir, receipt_sha, manifest_sha = _build_capture(
        tmp_path, decision_date=other_date
    )
    result = _validate(
        tmp_path,
        capture_dir,
        receipt_sha,
        manifest_sha,
        decision_date=other_date,
        cutoff=datetime.fromisoformat("2026-09-28T15:30:00+00:00"),
    )
    assert result["decision_date"] == "2026-09-28"
    assert result["status"] == "validated"


@pytest.mark.parametrize(
    ("venue", "mismatch", "expected_code"),
    [
        ("TWSE", "start", "twse_mi_index_capture_date_mismatch"),
        ("TWSE", "end", "twse_mi_index_capture_date_mismatch"),
        ("TPEx", "start", "tpex_daily_quotes_capture_date_mismatch"),
        ("TPEx", "end", "tpex_daily_quotes_capture_date_mismatch"),
    ],
)
def test_capture_start_and_end_taipei_dates_must_match_decision_date(
    tmp_path: Path, venue: str, mismatch: str, expected_code: str
) -> None:
    decision_date = date(2026, 9, 28)
    capture_dir, _receipt_sha, manifest_sha = _build_capture(
        tmp_path, decision_date=decision_date
    )
    receipt_path = capture_dir / "capture_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    twse_capture, tpex_capture = receipt["captures"]
    next_twse_start = "2026-09-29T15:18:27.1665879+00:00"
    next_twse_end = "2026-09-29T15:18:27.8257766+00:00"
    next_tpex_start = "2026-09-29T15:18:27.8800087+00:00"
    next_tpex_end = "2026-09-29T15:18:31.0739265+00:00"
    if venue == "TWSE":
        if mismatch == "start":
            twse_capture["capture_start_utc"] = next_twse_start
        twse_capture["capture_end_utc"] = next_twse_end
        tpex_capture["capture_start_utc"] = next_tpex_start
        tpex_capture["capture_end_utc"] = next_tpex_end
    elif mismatch == "start":
        tpex_capture["capture_start_utc"] = next_tpex_start
        tpex_capture["capture_end_utc"] = next_tpex_end
    else:
        tpex_capture["capture_end_utc"] = next_tpex_end
    receipt["finished_at_utc"] = "2026-09-29T15:18:31.1063917+00:00"
    receipt_bytes = _json_bytes(receipt)
    receipt_path.write_bytes(receipt_bytes)

    with pytest.raises(CaptureValidationError) as error:
        _validate(
            tmp_path,
            capture_dir,
            _sha(receipt_bytes),
            manifest_sha,
            decision_date=decision_date,
            cutoff=datetime.fromisoformat("2026-09-29T15:30:00+00:00"),
        )

    assert error.value.code == expected_code


def test_future_cutoff_is_rejected(tmp_path: Path) -> None:
    capture_dir, receipt_sha, manifest_sha = _build_capture(tmp_path)
    future_cutoff = datetime.now(timezone.utc) + timedelta(minutes=5)
    with pytest.raises(CaptureValidationError) as error:
        _validate(
            tmp_path,
            capture_dir,
            receipt_sha,
            manifest_sha,
            cutoff=future_cutoff,
        )
    assert error.value.code == "cutoff_in_future"


def test_capture_outside_qa_root_is_rejected(tmp_path: Path) -> None:
    outside_root = tmp_path / "outside"
    outside_root.mkdir()
    capture_dir, receipt_sha, manifest_sha = _build_capture(outside_root)
    with pytest.raises(CaptureValidationError) as error:
        _validate(tmp_path, capture_dir, receipt_sha, manifest_sha)
    assert error.value.code == "capture_outside_qa_root"


def test_hardlinked_raw_file_is_rejected(tmp_path: Path) -> None:
    capture_dir, receipt_sha, manifest_sha = _build_capture(tmp_path)
    raw_path = capture_dir / "twse_mi_index_20260929.json"
    link_path = capture_dir / "second-link.json"
    try:
        os.link(raw_path, link_path)
    except OSError as error:
        pytest.skip(f"目前檔案系統不支援 hardlink 測試：{error}")

    with pytest.raises(CaptureValidationError) as error:
        _validate(tmp_path, capture_dir, receipt_sha, manifest_sha)

    assert error.value.code == "twse_mi_index_raw_hardlink_rejected"


def test_reparse_component_is_rejected_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from data_module import wp5_official_daily_capture_validator as validator

    capture_dir, receipt_sha, manifest_sha = _build_capture(tmp_path)
    original = validator._is_reparse_point
    resolved_capture = capture_dir.resolve()
    monkeypatch.setattr(
        validator,
        "_is_reparse_point",
        lambda path: path == resolved_capture or original(path),
    )

    with pytest.raises(CaptureValidationError) as error:
        _validate(tmp_path, capture_dir, receipt_sha, manifest_sha)

    assert error.value.code == "path_reparse_component"


def test_reparse_capture_directory_is_rejected_when_supported(tmp_path: Path) -> None:
    outside_root = tmp_path / "external"
    outside_root.mkdir()
    _capture, receipt_sha, manifest_sha = _build_capture(outside_root)
    qa_root = tmp_path / "output" / "qa"
    qa_root.mkdir(parents=True)
    link = qa_root / CAPTURE_DIRECTORY_NAME
    try:
        link.symlink_to(
            outside_root / "output" / "qa" / CAPTURE_DIRECTORY_NAME,
            target_is_directory=True,
        )
    except OSError as error:
        pytest.skip(f"目前 Windows 權限不允許建立 symlink 測試：{error}")

    with pytest.raises(CaptureValidationError) as error:
        _validate(tmp_path, link, receipt_sha, manifest_sha)

    assert error.value.code == "path_reparse_component"


def test_cli_emits_json_and_does_not_write_capture_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from scripts import qa_validate_wp5_official_daily_capture as cli

    capture_dir, receipt_sha, manifest_sha = _build_capture(tmp_path)
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    before = sorted(path.name for path in capture_dir.iterdir())

    result = cli.main(
        [
            "--capture-dir", str(capture_dir),
            "--expected-receipt-sha256", receipt_sha,
            "--expected-manifest-sha256", manifest_sha,
            "--decision-date", "2026-09-29",
            "--cutoff-utc", "2026-09-29T15:30:00Z",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert result == 0
    assert output["status"] == "validated"
    assert output["evidence_kind"] == "official_same_day_market_activity_observed"
    assert sorted(path.name for path in capture_dir.iterdir()) == before
