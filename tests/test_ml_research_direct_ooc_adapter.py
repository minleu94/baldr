"""Unit and integration tests for Direct/OOC Research Adapter and Consumer."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import gzip
import json
from pathlib import Path
from typing import Any, Literal, Sequence, cast
import pytest

from data_module.ml_research_direct_ooc_adapter import (
    RESEARCH_ADAPTED_RAW_SCHEMA_VERSION,
    RESEARCH_ADAPTER_RECEIPT_SCHEMA_VERSION,
    RESEARCH_DIRECT_STORE_RECEIPT_SCHEMA_VERSION,
    ResearchAdaptRequest,
    ResearchAdapterError,
    ResearchDirectNumericStoreConsumer,
    ResearchDirectOOCAdapter,
    load_verified_ml_research_numeric_artifact,
)
import data_module.ml_research_direct_ooc_adapter as adapter_module
import data_module.ml_revision_aware_raw_candidate as raw_module
from data_module.ml_revision_aware_raw_candidate import (
    RevisionAwareRawCandidateBuilder,
    RevisionAwareRawRequest,
)
from data_module.ml_research_output_boundary import resolve_ml_research_output_path
from data_module.ml_daily_source_row_research_projection import _project_tpex_rows
from scripts.scheduled import current_stock_research_cycle as current_cycle
from tests.ml_research_test_support import install_test_revision_gate, write_snapshot_context_receipt


def _research(root: Path, *parts: str) -> Path:
    return root / "output" / "ml_research" / Path(*parts)


@pytest.fixture(autouse=True)
def _research_path_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def resolver(
        path: Path,
        *,
        repository_root: Path | None = None,
        extra_forbidden_roots: Sequence[Path] = (),
        access: Literal["read", "write"] = "read",
    ) -> Path:
        (tmp_path / "output" / "ml_research").mkdir(parents=True, exist_ok=True)
        return resolve_ml_research_output_path(
            path,
            repository_root=repository_root or tmp_path,
            extra_forbidden_roots=extra_forbidden_roots,
            access=access,
        )
    monkeypatch.setattr(adapter_module, "resolve_ml_research_output_path", resolver)
    monkeypatch.setattr(raw_module, "resolve_ml_research_output_path", resolver)
    install_test_revision_gate(monkeypatch)


def _snapshot_context(db_path: Path, root: Path) -> tuple[Path, str]:
    return write_snapshot_context_receipt(
        db_path, root, completed_at="2026-09-30T09:00:00+00:00"
    )


def _setup_revision_aware_candidate(root: Path) -> Path:
    import sqlite3
    db_path = root / "raw_db.sqlite"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE daily_prices (
            證券代號 TEXT NOT NULL,
            日期 TEXT NOT NULL,
            開盤價 TEXT,
            最高價 TEXT,
            最低價 TEXT,
            收盤價 TEXT,
            成交股數 INTEGER,
            成交金額 INTEGER,
            成交筆數 INTEGER,
            PRIMARY KEY (證券代號, 日期)
        )
    """)
    rows = [
        ("2330", "2026-09-29", "980.00", "985.00", "975.00", "982.00", 25000000, 24500000000, 35000),
        ("2330", "2026-09-30", "982.00", "990.00", "980.00", "988.00", 28000000, 27600000000, 40000),
    ]
    cur.executemany("INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()

    candidate_out = _research(root, "candidate_raw")
    candidate_custody = _research(root, "candidate_custody")
    context_path, context_sha = _snapshot_context(db_path, root)

    req = RevisionAwareRawRequest(
        snapshot_db=db_path,
        output_dir=candidate_out,
        custody_dir=candidate_custody,
        decision_at="2026-09-30T10:00:00Z",
        years=(2026,),
        snapshot_context_receipt_path=context_path,
        expected_snapshot_context_receipt_sha256=context_sha,
        now_provider=lambda: datetime.fromisoformat("2026-09-30T10:05:00+00:00"),
    )
    result = RevisionAwareRawCandidateBuilder(req).build()
    return result.manifest_path


def _setup_daily_projection_candidate(
    root: Path,
    *,
    source_available_at: str = "2026-10-02T11:20:15.011784+00:00",
    first_row_overrides: dict[str, Any] | None = None,
) -> Path:
    """建立可攜式契約 fixture；數值取自已讀回 QA 代表列，不是新擷取。"""
    proj_dir = root / "daily_projection_raw"
    proj_dir.mkdir(parents=True, exist_ok=True)
    obs_file = proj_dir / "observations.jsonl"
    records = [
        {
            "symbol": "2330",
            "source_date": "2026-10-02",
            "source_available_at": source_available_at,
            "exact_numeric_values": {
                "開盤價": {"value_int": 250500, "scale": 100, "source_token": "2,505.00"},
                "最高價": {"value_int": 251500, "scale": 100, "source_token": "2,515.00"},
                "最低價": {"value_int": 249500, "scale": 100, "source_token": "2,495.00"},
                "收盤價": {"value_int": 250000, "scale": 100, "source_token": "2,500.00"},
                "成交股數": {"value_int": 15792206, "scale": 1, "source_token": "15,792,206"},
                "成交金額": {"value_int": 39508159297, "scale": 1, "source_token": "39,508,159,297"},
                "成交筆數": {"value_int": 65783, "scale": 1, "source_token": "65,783"},
            },
            "source_raw_response_sha256": "",
            "source_receipt_sha256": "",
            "source_row_index": 0,
            "venue": "twse",
        },
        {
            "symbol": "2317",
            "source_date": "2026-10-02",
            "source_available_at": source_available_at,
            "exact_numeric_values": {
                "開盤價": {"value_int": 25300, "scale": 100, "source_token": "253.00"},
                "最高價": {"value_int": 25300, "scale": 100, "source_token": "253.00"},
                "最低價": {"value_int": 25050, "scale": 100, "source_token": "250.50"},
                "收盤價": {"value_int": 25100, "scale": 100, "source_token": "251.00"},
                "成交股數": {"value_int": 30466967, "scale": 1, "source_token": "30,466,967"},
                "成交金額": {"value_int": 7654181137, "scale": 1, "source_token": "7,654,181,137"},
                "成交筆數": {"value_int": 32698, "scale": 1, "source_token": "32,698"},
            },
            "source_row_index": 1,
            "source_raw_response_sha256": "",
            "source_receipt_sha256": "",
            "venue": "twse",
        },
    ]
    for field_name, replacement in (first_row_overrides or {}).items():
        records[0]["exact_numeric_values"][field_name] = replacement
    raw_path = proj_dir / "raw_response.bin"
    receipt_path = proj_dir / "source_receipt.json"
    raw_path.write_bytes(b"raw fixture bytes")
    receipt_path.write_bytes(b"receipt fixture bytes")
    for record in records:
        record["source_raw_response_sha256"] = "sha256:" + hashlib.sha256(raw_path.read_bytes()).hexdigest()
        record["source_receipt_sha256"] = "sha256:" + hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    with obs_file.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    obs_sha = hashlib.sha256(obs_file.read_bytes()).hexdigest()

    manifest_payload = {
        "schema_version": "ml-daily-source-row-research-projection.v1",
        "source_date": "2026-10-02",
        "observations_file": {"path": "observations.jsonl", "sha256": "sha256:" + obs_sha, "bytes": obs_file.stat().st_size, "row_count": 2},
        "input_files": {
            "raw_response.bin": {"bytes": raw_path.stat().st_size, "sha256": "sha256:" + hashlib.sha256(raw_path.read_bytes()).hexdigest()},
            "source_receipt.json": {"bytes": receipt_path.stat().st_size, "sha256": "sha256:" + hashlib.sha256(receipt_path.read_bytes()).hexdigest()},
        },
        "research_only": True,
        "formal_dataset": False,
        "formal_credit": False,
    }
    canonical = json.dumps(manifest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest_payload["content_sha256"] = "sha256:" + hashlib.sha256(canonical).hexdigest()

    manifest_path = proj_dir / "manifest.json"
    manifest_bytes = json.dumps(manifest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)
    manifest_sha = "sha256:" + hashlib.sha256(manifest_bytes).hexdigest()
    (proj_dir / "completion_receipt.json").write_text(json.dumps({
        "schema_version": "ml-daily-source-row-research-completion.v1",
        "completion_status": "awaiting_terminal_revision_validation",
        "manifest_sha256": manifest_sha,
        "observations_sha256": "sha256:" + obs_sha,
    }), encoding="utf-8")
    (proj_dir / "runner_terminal_verification_receipt.json").write_text(json.dumps({
        "schema_version": "ml-daily-source-row-runner-terminal-receipt.v1",
        "terminal_status": "completed_research_only",
        "historical_pit_eligible": False,
        "features_included": False,
        "labels_included": False,
        "projection": {"manifest_sha256": manifest_sha, "observations_sha256": "sha256:" + obs_sha},
    }), encoding="utf-8")
    return manifest_path


def _setup_tpex_actual_header_projection_candidate(root: Path) -> Path:
    """Project an observed TPEx raw-header row through the production parser."""

    project_dir = root / "tpex_projection"
    raw_path = project_dir / "inputs" / "sources" / "tpex" / "raw_response.bin"
    receipt_path = project_dir / "inputs" / "sources" / "tpex" / "source_receipt.json"
    raw_path.parent.mkdir(parents=True)
    fields = [
        "代號", "名稱", "收盤 ", "漲跌", "開盤 ", "最高 ", "最低",
        "成交股數  ", " 成交金額(元)", " 成交筆數 ", "最後買價",
        "最後買量<br>(張數)", "最後賣價", "最後賣量<br>(張數)",
        "發行股數 ", "次日漲停價 ", "次日跌停價",
    ]
    row_values = [
        "3207", "耀勝", "39.75", "-0.95", "41.80", "41.80", "39.70",
        "245,000", "9,907,800", "180", "39.75", "5", "39.80", "2",
        "66,422,124", "43.70", "35.80",
    ]
    raw_bytes = json.dumps(
        {"tables": [{"date": "2026/10/02", "fields": fields, "data": [row_values]}]},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    receipt_bytes = b"fixture TPEx source receipt; no production evidence"
    raw_path.write_bytes(raw_bytes)
    receipt_path.write_bytes(receipt_bytes)
    raw_sha = "sha256:" + hashlib.sha256(raw_bytes).hexdigest()
    receipt_sha = "sha256:" + hashlib.sha256(receipt_bytes).hexdigest()
    rows, table_count = _project_tpex_rows(
        raw_bytes,
        source_date="2026-10-02",
        source_available_at="2026-10-02T11:20:18.576024+00:00",
        raw_sha256=raw_sha,
        receipt_sha256=receipt_sha,
        expected_row_count=1,
    )
    assert table_count == 1
    observations_path = project_dir / "observations.jsonl"
    observations_path.write_bytes(
        b"".join(
            json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            + b"\n"
            for item in rows
        )
    )
    observation_sha = "sha256:" + hashlib.sha256(observations_path.read_bytes()).hexdigest()
    input_files = {
        "inputs/sources/tpex/raw_response.bin": {
            "bytes": len(raw_bytes),
            "sha256": raw_sha,
        },
        "inputs/sources/tpex/source_receipt.json": {
            "bytes": len(receipt_bytes),
            "sha256": receipt_sha,
        },
    }
    manifest = {
        "schema_version": "ml-daily-source-row-research-projection.v1",
        "source_date": "2026-10-02",
        "observations_file": {
            "path": "observations.jsonl",
            "sha256": observation_sha,
            "bytes": observations_path.stat().st_size,
            "row_count": len(rows),
        },
        "input_files": input_files,
        "research_only": True,
        "formal_dataset": False,
        "formal_credit": False,
    }
    canonical = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    manifest["content_sha256"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
    manifest_path = project_dir / "manifest.json"
    manifest_bytes = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)
    manifest_sha = "sha256:" + hashlib.sha256(manifest_bytes).hexdigest()
    (project_dir / "completion_receipt.json").write_text(
        json.dumps(
            {
                "schema_version": "ml-daily-source-row-research-completion.v1",
                "completion_status": "awaiting_terminal_revision_validation",
                "manifest_sha256": manifest_sha,
                "observations_sha256": observation_sha,
            }
        ),
        encoding="utf-8",
    )
    (project_dir / "runner_terminal_verification_receipt.json").write_text(
        json.dumps(
            {
                "schema_version": "ml-daily-source-row-runner-terminal-receipt.v1",
                "terminal_status": "completed_research_only",
                "historical_pit_eligible": False,
                "features_included": False,
                "labels_included": False,
                "projection": {
                    "manifest_sha256": manifest_sha,
                    "observations_sha256": observation_sha,
                },
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def _adapter_request(candidate_manifest: Path, output_dir: Path) -> ResearchAdaptRequest:
    return ResearchAdaptRequest(
        raw_candidate_manifest_path=candidate_manifest,
        output_dir=output_dir,
        training_as_of="2026-10-03T00:30:00+00:00",
        expected_candidate_manifest_bytes_sha256="sha256:" + hashlib.sha256(candidate_manifest.read_bytes()).hexdigest(),
    )


def test_adapt_revision_aware_raw_candidate_success(tmp_path: Path) -> None:
    candidate_manifest = _setup_revision_aware_candidate(tmp_path)

    adapted_out = _research(tmp_path, "adapted_research_dataset")
    req = _adapter_request(candidate_manifest, adapted_out)
    adapter = ResearchDirectOOCAdapter(req)
    result = adapter.adapt()

    assert result.status == "verified_numeric_observations_ready"
    assert result.adapted_manifest_path.exists()
    assert result.adapter_receipt_path.exists()
    assert result.formal_release_v4_pointer_untouched is True
    assert result.row_count == 2

    # 檢視 adapter receipt
    receipt = json.loads(result.adapter_receipt_path.read_bytes().decode("utf-8"))
    assert receipt["schema_version"] == RESEARCH_ADAPTER_RECEIPT_SCHEMA_VERSION
    assert receipt["status"] == "verified_numeric_observations_ready"
    assert receipt["candidate_raw_manifest_hash"] == result.candidate_raw_manifest_hash
    assert receipt["adapted_manifest_hash"] == result.adapted_manifest_hash
    assert receipt["formal_release_v4_pointer_untouched"] is True
    assert receipt["formal_d_root_untouched"] is True
    assert receipt["row_count"] == 2

    # 檢視 adapted manifest
    manifest = json.loads(result.adapted_manifest_path.read_bytes().decode("utf-8"))
    assert manifest["schema_version"] == RESEARCH_ADAPTED_RAW_SCHEMA_VERSION
    assert manifest["safety"]["direct_ooc_research_compatible"] is False
    assert manifest["safety"]["formal_dataset"] is False
    assert manifest["safety"]["research_only"] is True
    assert manifest["direct_ooc_readiness"]["status"] == "blocked_insufficient_context_or_mature_history"
    assert manifest["shards"][0]["path"].startswith("shards/")


def test_adapt_daily_source_row_projection_success(tmp_path: Path) -> None:
    daily_proj_manifest = _setup_daily_projection_candidate(tmp_path)

    adapted_out = _research(tmp_path, "adapted_daily_dataset")
    req = _adapter_request(daily_proj_manifest, adapted_out)
    adapter = ResearchDirectOOCAdapter(req)
    result = adapter.adapt()

    assert result.status == "verified_numeric_observations_ready"
    assert result.row_count == 2
    assert result.formal_release_v4_pointer_untouched is True

    # 驗證產生的 gzip JSONL shard
    manifest = json.loads(result.adapted_manifest_path.read_bytes().decode("utf-8"))
    shard_path = result.adapted_manifest_path.parent / manifest["shards"][0]["path"]
    assert shard_path.exists()
    with gzip.open(shard_path, "rb") as gz:
        records = [json.loads(line.decode("utf-8")) for line in gz.readlines()]
    assert len(records) == 2
    raw_sha = "sha256:" + hashlib.sha256((daily_proj_manifest.parent / "raw_response.bin").read_bytes()).hexdigest()
    receipt_sha = "sha256:" + hashlib.sha256((daily_proj_manifest.parent / "source_receipt.json").read_bytes()).hexdigest()
    expected_features = {
        "daily_prices.開盤價", "daily_prices.最高價", "daily_prices.最低價",
        "daily_prices.收盤價", "daily_prices.成交股數", "daily_prices.成交金額",
        "daily_prices.成交筆數",
    }
    for r in records:
        assert r["table_name"] == "daily_prices"
        assert r["symbol"] in ("2330", "2317")
        feat_ids = [v["feature_id"] for v in r["values"]]
        assert set(feat_ids) == expected_features
        assert r["source_version"] == {
            "raw_response_sha256": raw_sha,
            "source_receipt_sha256": receipt_sha,
            "source_row_index": 0 if r["symbol"] == "2330" else 1,
        }
        assert r["missing_mask"] == []
        assert r["quality_blocked_mask"] == []
        assert r["staleness_mask"] == []
    numeric = {
        row["symbol"]: {value["feature_id"]: (value["value_int"], value["scale"]) for value in row["values"]}
        for row in records
    }
    assert numeric["2330"] == {
        "daily_prices.開盤價": (250500, 2),
        "daily_prices.最高價": (251500, 2),
        "daily_prices.最低價": (249500, 2),
        "daily_prices.收盤價": (250000, 2),
        "daily_prices.成交股數": (15792206, 0),
        "daily_prices.成交金額": (39508159297, 0),
        "daily_prices.成交筆數": (65783, 0),
    }
    assert {item["feature_id"]: item["scale"] for item in manifest["features"]} == {
        "daily_prices.開盤價": 2,
        "daily_prices.最高價": 2,
        "daily_prices.最低價": 2,
        "daily_prices.收盤價": 2,
        "daily_prices.成交股數": 0,
        "daily_prices.成交金額": 0,
        "daily_prices.成交筆數": 0,
    }


def test_daily_projection_future_clock_and_noninteger_value_rejected(tmp_path: Path) -> None:
    future_manifest = _setup_daily_projection_candidate(
        tmp_path / "future",
        source_available_at="2026-10-03T00:31:00+00:00",
    )
    with pytest.raises(ResearchAdapterError, match="after the explicit freeze"):
        ResearchDirectOOCAdapter(_adapter_request(future_manifest, _research(tmp_path, "future_out"))).adapt()

    noninteger_manifest = _setup_daily_projection_candidate(
        tmp_path / "noninteger",
        first_row_overrides={"收盤價": {"value_int": 250000.0, "scale": 100, "source_token": "2500.00"}},
    )
    with pytest.raises(ResearchAdapterError, match="value_int must be a strict integer"):
        ResearchDirectOOCAdapter(_adapter_request(noninteger_manifest, _research(tmp_path, "noninteger_out"))).adapt()


def test_daily_projection_partial_value_keeps_exact_missing_mask(tmp_path: Path) -> None:
    partial_manifest = _setup_daily_projection_candidate(tmp_path, first_row_overrides={"成交筆數": None})
    adapted = ResearchDirectOOCAdapter(
        _adapter_request(partial_manifest, _research(tmp_path, "partial_out"))
    ).adapt()
    manifest = json.loads(adapted.adapted_manifest_path.read_text(encoding="utf-8"))
    shard = adapted.adapted_manifest_path.parent / manifest["shards"][0]["path"]
    with gzip.open(shard, "rt", encoding="utf-8") as stream:
        records = [json.loads(line) for line in stream]
    partial = next(row for row in records if row["symbol"] == "2330")
    assert partial["missing_mask"] == ["daily_prices.成交筆數"]
    assert "daily_prices.成交筆數" not in {value["feature_id"] for value in partial["values"]}
    assert len(partial["values"]) == 6


def test_research_direct_numeric_store_consumption(tmp_path: Path) -> None:
    candidate_manifest = _setup_revision_aware_candidate(tmp_path)
    adapted_out = _research(tmp_path, "adapted_research_dataset")

    adapter = ResearchDirectOOCAdapter(
        _adapter_request(candidate_manifest, adapted_out)
    )
    adapt_result = adapter.adapt()

    store_out = _research(tmp_path, "research_direct_numeric_store")
    consumer = ResearchDirectNumericStoreConsumer(
        adapter_receipt_path=adapt_result.adapter_receipt_path,
        output_store_dir=store_out,
        training_as_of="2026-10-03T00:30:00+00:00",
    )
    consumption_receipt = consumer.build_store()

    assert consumption_receipt["status"] == "verified_numeric_observations_ready"
    assert consumption_receipt["candidate_manifest_bytes_sha256"] == json.loads(adapt_result.adapter_receipt_path.read_text(encoding="utf-8"))["candidate_manifest_bytes_sha256"]
    assert consumption_receipt["adapted_manifest_canonical_sha256"] == adapt_result.adapted_manifest_hash
    assert consumption_receipt["formal_release_v4_pointer_untouched"] is True
    assert consumption_receipt["formal_oos_allowed"] is False
    assert consumption_receipt["production_alpha_bp"] == 0

    assert (store_out / "store_metadata.json").exists()
    assert (store_out / "feature_registry.json").exists()
    assert (store_out / "consumption_receipt.json").exists()
    assert consumption_receipt["direct_ooc_status"] == "blocked_insufficient_context_or_mature_history"

    loaded = load_verified_ml_research_numeric_artifact(
        store_out / "consumption_receipt.json",
        expected_consumption_receipt_sha256="sha256:" + hashlib.sha256((store_out / "consumption_receipt.json").read_bytes()).hexdigest(),
        expected_candidate_manifest_bytes_sha256=consumption_receipt["candidate_manifest_bytes_sha256"],
        expected_adapted_manifest_canonical_sha256=consumption_receipt["adapted_manifest_canonical_sha256"],
        expected_feature_registry_sha256=consumption_receipt["feature_registry_sha256"],
        available_at_or_before=datetime.fromisoformat(consumption_receipt["current_observation_freeze"]),
    )
    assert loaded.status == "verified_numeric_observations_ready"
    assert loaded.historical_pit_eligible is False
    assert loaded.observations
    assert all(type(value["value_int"]) is int for row in loaded.observations for value in row.values)
    assert {value["scale"] for row in loaded.observations for value in row.values} == {0, 2}
    with pytest.raises(TypeError):
        cast(Any, loaded.observations[0].values[0])["value_int"] = -1
    with pytest.raises(TypeError):
        cast(Any, loaded.feature_registry[0])["scale"] = 99
    with pytest.raises(TypeError):
        cast(Any, loaded.source_pins)["candidate_manifest_bytes_sha256"] = "sha256:" + "0" * 64
    audit_copy = loaded.audit_payload()
    json.dumps(audit_copy, ensure_ascii=False)
    audit_copy["observations"][0]["values"][0]["value_int"] = -999
    assert loaded.observations[0].values[0]["value_int"] != -999


def test_tampered_candidate_manifest_hash_rejected(tmp_path: Path) -> None:
    candidate_manifest = _setup_revision_aware_candidate(tmp_path)

    adapted_out = _research(tmp_path, "tampered_out")
    req = ResearchAdaptRequest(
        raw_candidate_manifest_path=candidate_manifest,
        output_dir=adapted_out,
        training_as_of="2026-09-30T10:00:00+00:00",
        expected_candidate_manifest_bytes_sha256="sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
    )
    with pytest.raises(ResearchAdapterError, match="candidate manifest bytes SHA-256 mismatch"):
        ResearchDirectOOCAdapter(req).adapt()


def test_adapter_cli_requires_and_reports_manifest_actual_bytes_pin(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    candidate_manifest = _setup_daily_projection_candidate(tmp_path)
    candidate_sha = hashlib.sha256(candidate_manifest.read_bytes()).hexdigest()
    output_dir = _research(tmp_path, "adapter_cli_output")
    argv = [
        "--raw-candidate-manifest", str(candidate_manifest),
        "--output-dir", str(output_dir),
        "--training-as-of", "2026-10-03T00:30:00+00:00",
        "--expected-candidate-manifest-bytes-sha256", "sha256:" + candidate_sha,
    ]
    assert adapter_module.main(argv) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "verified_numeric_observations_ready"
    assert output["direct_ooc_status"] == "blocked_insufficient_context_or_mature_history"
    assert output["source_revision_qualification"] == "unverified_requires_separate_strict_inspection"

    bad_output = _research(tmp_path, "adapter_cli_bad_pin")
    bad_argv = [*argv]
    bad_argv[bad_argv.index(str(output_dir))] = str(bad_output)
    bad_argv[-1] = "sha256:" + "0" * 64
    assert adapter_module.main(bad_argv) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["status"] == "blocked"
    assert "SHA-256 mismatch" in error["message"]
    assert not bad_output.exists()


def test_isolation_guard_rejects_release_v4_target(tmp_path: Path) -> None:
    candidate_manifest = _setup_revision_aware_candidate(tmp_path)
    prohibited_out = tmp_path / "release_v4" / "illegal_target"

    with pytest.raises(ResearchAdapterError, match="research writes must be inside the configured active ML research root"):
        ResearchAdaptRequest(
            raw_candidate_manifest_path=candidate_manifest,
            output_dir=prohibited_out,
            training_as_of="2026-09-30T10:00:00+00:00",
        )


def test_consumer_rejects_corrupted_adapter_receipt(tmp_path: Path) -> None:
    candidate_manifest = _setup_revision_aware_candidate(tmp_path)
    adapted_out = _research(tmp_path, "adapted_research_dataset")

    adapt_result = ResearchDirectOOCAdapter(
        _adapter_request(candidate_manifest, adapted_out)
    ).adapt()

    # 篡改 receipt
    receipt_path = adapt_result.adapter_receipt_path
    data = json.loads(receipt_path.read_bytes().decode("utf-8"))
    data["adapted_manifest_hash"] = "sha256:corruptedhash000000000000000000000000000000000000000000000000"
    receipt_path.write_bytes(json.dumps(data).encode("utf-8"))

    consumer = ResearchDirectNumericStoreConsumer(
        adapter_receipt_path=receipt_path,
        output_store_dir=_research(tmp_path, "fail_store"),
        training_as_of="2026-09-30T10:00:00+00:00",
    )
    with pytest.raises(ResearchAdapterError, match="SHA-256 pin"):
        consumer.build_store()


def test_portable_daily_projection_fixture_full_chain(tmp_path: Path) -> None:
    """不依賴本機 QA 路徑，只驗代表數值與 current-observed 合約。"""
    candidate = _setup_daily_projection_candidate(tmp_path)
    adapted = ResearchDirectOOCAdapter(
        _adapter_request(candidate, _research(tmp_path, "portable_adapted"))
    ).adapt()
    store_out = _research(tmp_path, "portable_store")
    freeze = datetime.fromisoformat("2026-10-03T00:30:00+00:00")
    receipt = ResearchDirectNumericStoreConsumer(
        adapter_receipt_path=adapted.adapter_receipt_path,
        output_store_dir=store_out,
        training_as_of=freeze.isoformat(),
    ).build_store()
    loaded = load_verified_ml_research_numeric_artifact(
        store_out / "consumption_receipt.json",
        expected_consumption_receipt_sha256="sha256:" + hashlib.sha256((store_out / "consumption_receipt.json").read_bytes()).hexdigest(),
        expected_candidate_manifest_bytes_sha256=receipt["candidate_manifest_bytes_sha256"],
        expected_adapted_manifest_canonical_sha256=receipt["adapted_manifest_canonical_sha256"],
        expected_feature_registry_sha256=receipt["feature_registry_sha256"],
        available_at_or_before=freeze,
    )
    assert receipt["record_count"] == 2
    assert loaded.status == "verified_numeric_observations_ready"
    assert loaded.historical_pit_eligible is False
    assert loaded.observations[0].event_date == "2026-10-02"
    assert loaded.observations[0].available_at.isoformat() == "2026-10-02T11:20:15.011784+00:00"
    assert len(loaded.observations[0].values) == 7


def test_tpex_raw_header_projects_into_numeric_store_and_cycle_identity(
    tmp_path: Path,
) -> None:
    candidate = _setup_tpex_actual_header_projection_candidate(tmp_path)
    projected = json.loads(
        (candidate.parent / "observations.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    assert projected["venue"] == "tpex"
    assert "開盤 " in projected["exact_numeric_values"]
    assert " 成交金額(元)" in projected["exact_numeric_values"]

    adapted = ResearchDirectOOCAdapter(
        _adapter_request(candidate, _research(tmp_path, "tpex_adapted"))
    ).adapt()
    store_root = _research(tmp_path, "tpex_store")
    store_receipt = ResearchDirectNumericStoreConsumer(
        adapter_receipt_path=adapted.adapter_receipt_path,
        output_store_dir=store_root,
        training_as_of="2026-10-03T00:30:00+00:00",
    ).build_store()
    assert store_receipt["feature_value_count"] == 7

    store_registry_path = store_root / "feature_registry.json"
    registry = json.loads(store_registry_path.read_text(encoding="utf-8"))
    expected_feature_ids = set(adapter_module.DAILY_PRICE_FEATURE_INFO)
    assert {item["feature_id"] for item in registry} == expected_feature_ids
    stored_shard = store_receipt["stored_shards"][0]
    shard_path = store_root / stored_shard["path"]
    with gzip.open(shard_path, "rt", encoding="utf-8") as stream:
        adapted_row = json.loads(next(stream))
    assert adapted_row["symbol"] == "3207"
    assert adapted_row["missing_mask"] == []
    values_by_id = {value["feature_id"]: value for value in adapted_row["values"]}
    assert set(values_by_id) == expected_feature_ids
    assert values_by_id[adapter_module.DAILY_PRICE_FEATURE_IDS["open"]]["value_int"] == 4180
    amount = values_by_id[adapter_module.DAILY_PRICE_FEATURE_IDS["amount"]]
    assert (amount["value_int"], amount["scale"], amount["unit"]) == (9907800, 0, "TWD")

    registry_bytes = store_registry_path.read_bytes()
    terminal = {
        "feature_registry_path": str(store_registry_path.resolve()),
        "feature_registry_sha256": store_receipt["feature_registry_sha256"],
        "feature_registry_bytes_sha256": "sha256:" + hashlib.sha256(registry_bytes).hexdigest(),
        "adapted_manifest_path": str(adapted.adapted_manifest_path.resolve()),
        "adapted_manifest_sha256": store_receipt["adapted_manifest_bytes_sha256"],
        "adapted_manifest_canonical_sha256": store_receipt[
            "adapted_manifest_canonical_sha256"
        ],
        "stored_shards": [
            {
                **shard,
                "path": str((store_root / shard["path"]).resolve()),
            }
            for shard in store_receipt["stored_shards"]
        ],
    }
    semantic_identity = current_cycle._current_b_semantic_identity(
        b_terminal=terminal,
        symbols=["3207"],
        source_date="2026-10-02",
        repository_root=tmp_path,
    )
    assert semantic_identity["feature_registry_sha256"] == store_receipt[
        "feature_registry_sha256"
    ]
    assert semantic_identity["current_vector_semantic_sha256"].startswith("sha256:")


def test_projection_source_mapping_fails_closed_on_ambiguous_alias_and_unknown_unit() -> None:
    with pytest.raises(ResearchAdapterError, match="ambiguous"):
        adapter_module._projection_exact_value(
            {
                "開盤 ": {"state": "numeric", "value_int": 4180, "scale": 100},
                "開盤": {"state": "numeric", "value_int": 4190, "scale": 100},
            },
            venue="tpex",
            feature_id=adapter_module.DAILY_PRICE_FEATURE_IDS["open"],
        )

    assert adapter_module._projection_exact_value(
        {
            "成交金額(千元)": {
                "state": "numeric",
                "value_int": 9908,
                "scale": 1,
            }
        },
        venue="tpex",
        feature_id=adapter_module.DAILY_PRICE_FEATURE_IDS["amount"],
    ) is None
