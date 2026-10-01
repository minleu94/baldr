from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import sqlite3

import pytest

from data_module.formal_market_revision import RECEIPT_DIR
from data_module.ml_daily_source_row_research_projection import (
    MLSourceRowProjectionError,
    _exact_decimal,
    _project_twse_rows,
    _project_tpex_rows,
    _strict_json_object,
    project_daily_source_rows,
)
from data_module.ml_prospective_daily_price_capture import (
    capture_prospective_daily_price_candidate,
)
from data_module.official_daily_price_custody import persist_official_daily_price_response
from data_module.tpex_daily_price_backfill import normalize_tpex_daily_price_rows
from data_module.tpex_daily_price_source import _rows_from_after_trading_response
from scripts import project_ml_daily_source_rows as cli


SOURCE_DATE = "2026-09-30"
TWSE_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
TPEX_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc"


def _write_revision(database: Path) -> None:
    data_root = database.parent.parent
    run_root = data_root / RECEIPT_DIR / "fixture-revision"
    run_root.mkdir(parents=True)
    identity = str(database.resolve())
    plan = {
        "schema_version": "formal-market-repair.v1",
        "database_path": identity,
        "source_start_date": "2014-01-02",
        "source_end_date": "2026-09-23",
    }
    plan_raw = json.dumps(plan, sort_keys=True).encode("utf-8")
    plan_hash = hashlib.sha256(plan_raw).hexdigest()
    journal_raw = json.dumps(
        {"schema_version": "formal-market-repair.v1", "plan_sha256": plan_hash},
        sort_keys=True,
    ).encode("utf-8")
    receipt_raw = json.dumps(
        {"schema_version": "formal-market-repair.v1", "plan_sha256": plan_hash},
        sort_keys=True,
    ).encode("utf-8")
    (run_root / "plan.json").write_bytes(plan_raw)
    (run_root / "journal.json").write_bytes(journal_raw)
    (run_root / "receipt.json").write_bytes(receipt_raw)
    marker = {
        "schema_version": "formal-market-revision.v1",
        "database_path": identity,
        "source_start_date": "2014-01-02",
        "source_end_date": "2026-09-23",
        "state": "applied",
        "receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
    }
    (run_root / "revision.json").write_text(
        json.dumps(marker, sort_keys=True), encoding="utf-8"
    )


def _source_payloads() -> tuple[dict[str, object], dict[str, object]]:
    twse_fields = [
        "證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額", "開盤價",
        "最高價", "最低價", "收盤價", "漲跌(+/-)", "漲跌價差", "最後揭示買價",
        "最後揭示買量", "最後揭示賣價", "最後揭示賣量", "本益比",
    ]
    twse_row = [
        "2330", "台積電", "1,234", "12", "1,000,000", "13.00", "13.50",
        "12.75", "13.25", "", "0.25", "13.20", "10", "13.25", "12", "20.00",
    ]
    tpex_fields = [
        "代號", "名稱", "收盤 ", "漲跌", "開盤 ", "最高 ", "最低",
        "成交股數  ", " 成交金額(元)", " 成交筆數 ", "最後買價",
        "最後買量<br>(張數)", "最後賣價", "最後賣量<br>(張數)",
        "發行股數 ", "次日漲停價 ", "次日跌停價 ",
    ]
    tpex_row = [
        "6488", "環球晶", "12.50", "+0.25", "12.25", "12.75", "12.25",
        "1,234", "15,425", "12", "12.50", "10", "12.55", "11",
        "100,000", "13.25", "11.75",
    ]
    return (
        {
            "stat": "OK",
            "date": "20260930",
            "tables": [{"fields": twse_fields, "data": [twse_row]}],
        },
        {
            "tables": [
                {
                    "date": "2026/09/30",
                    "fields": tpex_fields,
                    "data": [tpex_row],
                }
            ]
        },
    )


def _write_source(source_root: Path, venue: str, payload: dict[str, object]) -> None:
    source_root.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    captured_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    if venue == "twse":
        fields = payload["tables"][0]["fields"]  # type: ignore[index]
        requested_url = final_url = TWSE_URL
        parameters = {"date": SOURCE_DATE.replace("-", ""), "type": "ALL", "response": "json"}
        source_id = "twse.mi_index.daily_price"
        parser_id = "twse.mi_index.v1"
        columns = list(fields)
    else:
        raw_rows = _rows_from_after_trading_response(
            payload,
            fallback_date=SOURCE_DATE.replace("-", ""),
        )
        normalized = normalize_tpex_daily_price_rows(
            raw_rows,
            fallback_date=SOURCE_DATE.replace("-", ""),
            strict=False,
        )
        requested_url = final_url = TPEX_URL
        parameters = {
            "date": "2026/09/30",
            "type": "EW",
            "response": "json",
        }
        source_id = "tpex.daily_close_quotes"
        parser_id = "tpex.daily_close_quotes.v1"
        columns = list(normalized.rows[0].keys())
    persist_official_daily_price_response(
        output_root=source_root,
        venue=venue,
        source_id=source_id,
        source_date=SOURCE_DATE,
        requested_url=requested_url,
        final_url=final_url,
        request_parameters=parameters,
        http_status=200,
        response_headers={"content-type": "application/json"},
        raw_response=raw,
        captured_at=captured_at,
        row_count=1,
        source_columns=columns,
        parser_id=parser_id,
        historical_backfill_claimed=False,
    )


def _candidate(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, bytes]]:
    repo = tmp_path / "repo"
    repo.mkdir()
    database = repo / "data" / "sqlite" / "twstock.db"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE fixture (id INTEGER PRIMARY KEY)")
    _write_revision(database)
    source_root = repo / "source-custody"
    twse_payload, tpex_payload = _source_payloads()
    _write_source(source_root, "twse", twse_payload)
    _write_source(source_root, "tpex", tpex_payload)
    candidate_root = repo / "output" / "ml_prospective_daily_price_candidates"
    captured = capture_prospective_daily_price_candidate(
        source_output_root=source_root,
        database_path=database,
        source_date=SOURCE_DATE,
        candidate_root=candidate_root,
        preview_only=False,
    )
    assert captured["status"] == "captured"
    manifest_path = Path(str(captured["candidate_directory"])) / "manifest.json"
    source_bytes = {
        str(path.relative_to(repo)): path.read_bytes()
        for path in source_root.rglob("*")
        if path.is_file()
    }
    return repo, database, manifest_path, source_bytes


def _short_case_root(factory: pytest.TempPathFactory, name: str) -> Path:
    path = factory.getbasetemp() / name
    path.mkdir()
    return path


def test_decimal_projection_preserves_exact_integer_scale_and_missing_state() -> None:
    fractional_price = _exact_decimal("13.25", field="price", integer_only=False)
    assert fractional_price == {
        "raw_value": "13.25",
        "state": "numeric",
        "value_int": 1325,
        "scale": 100,
    }
    missing = _exact_decimal("--", field="shares", integer_only=True)
    assert missing["state"] == "source_missing"
    assert missing["value_int"] is None
    assert missing["scale"] is None
    with pytest.raises(MLSourceRowProjectionError, match="fractional"):
        _exact_decimal("12.5", field="shares", integer_only=True)
    with pytest.raises(MLSourceRowProjectionError, match="precision/exponent"):
        _exact_decimal("1e19", field="price", integer_only=False)


def test_tpex_price_limits_allow_decimal_values_but_integer_fields_do_not() -> None:
    _twse_payload, payload = _source_payloads()
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    rows, table_count = _project_tpex_rows(
        raw,
        source_date=SOURCE_DATE,
        source_available_at="2026-09-30T08:00:00+00:00",
        raw_sha256="sha256:" + "a" * 64,
        receipt_sha256="sha256:" + "b" * 64,
        expected_row_count=1,
    )
    assert table_count == 1
    exact_values = rows[0]["exact_numeric_values"]
    assert exact_values["次日漲停價 "]["value_int"] == 1325  # type: ignore[index]
    assert exact_values["次日漲停價 "]["scale"] == 100  # type: ignore[index]
    assert exact_values["次日跌停價 "]["value_int"] == 1175  # type: ignore[index]

    table = payload["tables"][0]  # type: ignore[index]
    row = table["data"][0]  # type: ignore[index]
    row[7] = "1.5"
    fractional_shares = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with pytest.raises(MLSourceRowProjectionError, match="integer field is fractional"):
        _project_tpex_rows(
            fractional_shares,
            source_date=SOURCE_DATE,
            source_available_at="2026-09-30T08:00:00+00:00",
            raw_sha256="sha256:" + "a" * 64,
            receipt_sha256="sha256:" + "b" * 64,
            expected_row_count=1,
        )


def test_tpex_known_change_annotation_is_preserved_without_numeric_interpretation() -> None:
    _twse_payload, payload = _source_payloads()
    table = payload["tables"][0]  # type: ignore[index]
    table["data"][0][3] = "除息"  # type: ignore[index]
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    rows, table_count = _project_tpex_rows(
        raw,
        source_date=SOURCE_DATE,
        source_available_at="2026-09-30T08:00:00+00:00",
        raw_sha256="sha256:" + "a" * 64,
        receipt_sha256="sha256:" + "b" * 64,
        expected_row_count=1,
    )

    annotation = rows[0]["exact_numeric_values"]["漲跌"]  # type: ignore[index]
    assert table_count == 1
    assert rows[0]["symbol"] == "6488"
    assert rows[0]["source_values"]["漲跌"] == "除息"  # type: ignore[index]
    assert annotation["state"] == "source_annotation"  # type: ignore[index]
    assert annotation["source_text"] == "除息"  # type: ignore[index]
    assert annotation["annotation_text"] == "除息"  # type: ignore[index]
    assert annotation["value_int"] is None  # type: ignore[index]
    assert annotation["scale"] is None  # type: ignore[index]


def test_tpex_unknown_change_annotation_remains_fail_closed() -> None:
    _twse_payload, payload = _source_payloads()
    table = payload["tables"][0]  # type: ignore[index]
    table["data"][0][3] = "未核定文字標記"  # type: ignore[index]
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    with pytest.raises(MLSourceRowProjectionError, match="source numeric token is invalid: 漲跌"):
        _project_tpex_rows(
            raw,
            source_date=SOURCE_DATE,
            source_available_at="2026-09-30T08:00:00+00:00",
            raw_sha256="sha256:" + "a" * 64,
            receipt_sha256="sha256:" + "b" * 64,
            expected_row_count=1,
        )


def test_tpex_duplicate_raw_identity_fails_even_if_first_close_is_missing() -> None:
    _twse_payload, payload = _source_payloads()
    table = payload["tables"][0]  # type: ignore[index]
    first_row = list(table["data"][0])  # type: ignore[index]
    first_row[2] = "--"
    second_row = list(first_row)
    second_row[2] = "12.50"
    table["data"] = [first_row, second_row]  # type: ignore[index]
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    with pytest.raises(MLSourceRowProjectionError, match="duplicate symbol"):
        _project_tpex_rows(
            raw,
            source_date=SOURCE_DATE,
            source_available_at="2026-09-30T08:00:00+00:00",
            raw_sha256="sha256:" + "a" * 64,
            receipt_sha256="sha256:" + "b" * 64,
            expected_row_count=1,
        )


def test_twse_full_raw_table_rows_are_distinct_from_eligible_four_digit_scope() -> None:
    payload, _tpex_payload = _source_payloads()
    table = payload["tables"][0]  # type: ignore[index]
    template = list(table["data"][0])  # type: ignore[index]
    eligible_count = 1_095
    raw_count = 35_794
    rows: list[list[object]] = []
    for value in range(1, eligible_count + 1):
        row = list(template)
        row[0] = f"{value:04d}"
        rows.append(row)
    for value in range(raw_count - eligible_count):
        row = list(template)
        row[0] = f"INDEX-EQUITY-{value:05d}"
        rows.append(row)
    table["data"] = rows  # type: ignore[index]
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    projected, source_table_count = _project_twse_rows(
        raw,
        source_date=SOURCE_DATE,
        source_available_at="2026-09-30T08:00:00+00:00",
        raw_sha256="sha256:" + "a" * 64,
        receipt_sha256="sha256:" + "b" * 64,
        expected_row_count=eligible_count,
    )

    assert source_table_count == raw_count
    assert len(projected) == eligible_count
    assert projected[0]["symbol"] == "0001"
    assert projected[-1]["symbol"] == f"{eligible_count:04d}"


def test_tpex_row_cap_rejects_oversized_source_before_projection() -> None:
    _twse_payload, payload = _source_payloads()
    table = payload["tables"][0]  # type: ignore[index]
    fields = table["fields"]  # type: ignore[index]
    table["data"] = [[""] * len(fields) for _ in range(50_001)]  # type: ignore[index]
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    with pytest.raises(MLSourceRowProjectionError, match="fields/rows are invalid"):
        _project_tpex_rows(
            raw,
            source_date=SOURCE_DATE,
            source_available_at="2026-09-30T08:00:00+00:00",
            raw_sha256="sha256:" + "a" * 64,
            receipt_sha256="sha256:" + "b" * 64,
            expected_row_count=1,
        )


@pytest.mark.parametrize(
    "raw",
    (
        b'{"value":1,"value":2}',
        b'{"value":NaN}',
        b'{"value":Infinity}',
    ),
)
def test_strict_input_json_rejects_duplicate_keys_and_nonfinite_values(raw: bytes) -> None:
    with pytest.raises(MLSourceRowProjectionError, match="JSON is invalid"):
        _strict_json_object(raw, "fixture")


def test_projection_preflight_is_no_write_and_binds_source_and_revision(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    tmp_path = _short_case_root(tmp_path_factory, "preflight")
    repo, database, manifest_path, source_before = _candidate(tmp_path)
    database_before = hashlib.sha256(database.read_bytes()).hexdigest()
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    result = project_daily_source_rows(
        candidate_manifest_path=manifest_path,
        expected_manifest_sha256=manifest_sha,
        repository_root=repo,
        now_provider=lambda: datetime.now(timezone.utc) + timedelta(seconds=1),
    )

    assert result["status"] == "preflight_passed_no_write"
    assert result["no_write"] is True
    assert result["projected_row_count"] == 2
    assert result["market_revision_cutoff_policy_evaluated"] is False
    assert result["formal_credit"] is False
    assert result["historical_pit_eligible"] is False
    assert result["direct_ooc_compatible"] is False
    assert not (repo / "output" / "qa" / "ml_daily_source_row_research_projections").exists()
    assert hashlib.sha256(database.read_bytes()).hexdigest() == database_before
    assert {
        str(path.relative_to(repo)): path.read_bytes()
        for path in (repo / "source-custody").rglob("*")
        if path.is_file()
    } == source_before


def test_projection_write_is_create_only_readback_verified_and_research_only(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    tmp_path = _short_case_root(tmp_path_factory, "write")
    repo, database, manifest_path, source_before = _candidate(tmp_path)
    database_before = hashlib.sha256(database.read_bytes()).hexdigest()
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    output_root = repo / "output" / "qa" / "ml_daily_source_row_research_projections"
    result = project_daily_source_rows(
        candidate_manifest_path=manifest_path,
        expected_manifest_sha256=manifest_sha,
        repository_root=repo,
        output_root=output_root,
        preview_only=False,
        now_provider=lambda: datetime.now(timezone.utc) + timedelta(seconds=1),
    )

    assert result["status"] == "completed_research_only"
    assert result["verification_completed_at"]
    root = Path(str(result["candidate_root"]))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    receipt = json.loads((root / "completion_receipt.json").read_text(encoding="utf-8"))
    assert manifest["source_numeric_representation"]["unit_claimed"] is False
    assert manifest["features_included"] is False
    assert manifest["labels_included"] is False
    assert manifest["model_use_claimed"] is False
    assert manifest["formal_credit"] is False
    assert receipt["completion_status"] == "awaiting_terminal_revision_validation"
    assert datetime.fromisoformat(str(result["verification_completed_at"])) >= datetime.fromisoformat(
        receipt["completion_started_at"]
    )
    records = [
        json.loads(line)
        for line in (root / "observations.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    tpex = next(item for item in records if item["venue"] == "tpex")
    assert tpex["exact_numeric_values"]["次日漲停價 "]["scale"] == 100
    assert hashlib.sha256(database.read_bytes()).hexdigest() == database_before
    assert {
        str(path.relative_to(repo)): path.read_bytes()
        for path in (repo / "source-custody").rglob("*")
        if path.is_file()
    } == source_before

    with pytest.raises(MLSourceRowProjectionError, match="explicit SHA-256 pin"):
        project_daily_source_rows(
            candidate_manifest_path=manifest_path,
            expected_manifest_sha256="0" * 64,
            repository_root=repo,
            output_root=output_root,
            preview_only=False,
        )


def test_projection_rejects_wrong_manifest_pin(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    tmp_path = _short_case_root(tmp_path_factory, "wrong-pin")
    repo, _database, manifest_path, _source_before = _candidate(tmp_path)
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    with pytest.raises(MLSourceRowProjectionError, match="explicit SHA-256 pin"):
        project_daily_source_rows(
            candidate_manifest_path=manifest_path,
            expected_manifest_sha256="f" * 64,
            repository_root=repo,
        )


def test_projection_leaves_no_success_receipt_when_revision_changes(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tmp_path = _short_case_root(tmp_path_factory, "revision-drift")
    import data_module.ml_daily_source_row_research_projection as projection

    repo, database, manifest_path, _source_before = _candidate(tmp_path)
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    original_binding = projection._revision_binding
    call_count = 0

    def changed_on_final_check(database_path: Path) -> dict[str, object]:
        nonlocal call_count
        call_count += 1
        binding = original_binding(database_path)
        if call_count == 5:
            binding = {**binding, "digest_sha256": "sha256:" + "0" * 64}
        return binding

    monkeypatch.setattr(projection, "_revision_binding", changed_on_final_check)
    output_root = repo / "output" / "qa" / "ml_daily_source_row_research_projections"
    with pytest.raises(MLSourceRowProjectionError, match="before projection completion"):
        project_daily_source_rows(
            candidate_manifest_path=manifest_path,
            expected_manifest_sha256=manifest_sha,
            repository_root=repo,
            output_root=output_root,
            preview_only=False,
        )
    candidate_roots = list(output_root.glob(f"{SOURCE_DATE}/*"))
    assert len(candidate_roots) == 1
    receipt = json.loads(
        (candidate_roots[0] / "completion_receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["completion_status"] == "awaiting_terminal_revision_validation"
    assert call_count == 5
    assert database.is_file()


@pytest.mark.parametrize(
    ("write_candidate", "expected_preview_only"),
    ((False, True), (True, False)),
)
def test_cli_is_no_write_unless_write_flag_is_explicit(
    write_candidate: bool,
    expected_preview_only: bool,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    observed: dict[str, object] = {}

    def project(**kwargs: object) -> dict[str, object]:
        observed.update(kwargs)
        return {"status": "fixture", "no_write": expected_preview_only}

    monkeypatch.setattr(cli, "project_daily_source_rows", project)
    argv = [
        "--candidate-manifest", "candidate/manifest.json",
        "--expected-manifest-sha256", "a" * 64,
    ]
    if write_candidate:
        argv.append("--write-candidate")

    assert cli.main(argv) == 0
    assert observed["preview_only"] is expected_preview_only
    assert observed["candidate_manifest_path"] == Path("candidate/manifest.json")
    assert json.loads(capsys.readouterr().out)["no_write"] is expected_preview_only


def test_cli_success_json_is_safe_for_legacy_windows_console_encoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_buffer = io.BytesIO()
    output_stream = io.TextIOWrapper(output_buffer, encoding="cp1252", errors="strict")
    monkeypatch.setattr(
        cli,
        "project_daily_source_rows",
        lambda **_kwargs: {"issuer": "綠電", "annotation": "除息", "status": "completed_research_only"},
    )
    monkeypatch.setattr(cli.sys, "stdout", output_stream)

    assert cli.main(
        ["--candidate-manifest", "candidate/manifest.json", "--expected-manifest-sha256", "a" * 64]
    ) == 0
    output_stream.flush()
    output = output_buffer.getvalue().decode("ascii")
    output_stream.detach()

    assert json.loads(output) == {
        "annotation": "除息",
        "issuer": "綠電",
        "status": "completed_research_only",
    }


def test_cli_error_json_is_safe_for_legacy_windows_console_encoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error_buffer = io.BytesIO()
    error_stream = io.TextIOWrapper(error_buffer, encoding="cp1252", errors="strict")

    def reject_projection(**_kwargs: object) -> dict[str, object]:
        raise MLSourceRowProjectionError("來源拒絕除息標記")

    monkeypatch.setattr(cli, "project_daily_source_rows", reject_projection)
    monkeypatch.setattr(cli.sys, "stderr", error_stream)

    assert cli.main(
        ["--candidate-manifest", "candidate/manifest.json", "--expected-manifest-sha256", "a" * 64]
    ) == 2
    error_stream.flush()
    error = error_buffer.getvalue().decode("ascii")
    error_stream.detach()

    assert json.loads(error) == {
        "error": "來源拒絕除息標記",
        "error_type": "MLSourceRowProjectionError",
        "status": "rejected",
    }


def test_decimal_token_type_guard_keeps_source_values_exact() -> None:
    parsed = _strict_json_object(b'{"numeric":1.25}', "fixture")
    assert parsed["numeric"] == Decimal("1.25")
    with pytest.raises(MLSourceRowProjectionError, match="float/bool cell"):
        _exact_decimal(1.25, field="price", integer_only=False)
    with pytest.raises(MLSourceRowProjectionError, match="preserved text token"):
        _exact_decimal(parsed["numeric"], field="price", integer_only=False)
