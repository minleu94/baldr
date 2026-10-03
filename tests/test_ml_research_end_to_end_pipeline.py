"""端到端全鏈路測試：ML Revision-Aware Research Pipeline.

涵蓋：
1. 路徑 A：市場修訂發生時，透過 PITYearShardExporter / build_ml_pit_year_shards
   搭配 allow_source_revision_research 產出研究年 shards，
   下游由 Direct Numeric Store 與 Raw-to-OOC Pipeline 消費（allow_research=True）全鏈貫通。
2. 路徑 B：單日來源列投影／前瞻捕獲候選資料，透過
   ResearchDirectOOCAdapter 適配為 Direct/OOC 相容規格，並透過
   ResearchDirectNumericStoreConsumer 建立隔離研究 Store 與不可變收據。
3. 安全與防護邊界：嚴禁輸出至 release_v4、零裸 float、未來函數防禦、Formal pointer 零污染。
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import gzip
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from typing import Any

import pytest

from data_module.ml_pit_year_shard_exporter import (
    PITYearShardExporter,
    PITYearShardBuildRequest,
)
from data_module.portfolio_ml_direct_numeric_store import (
    PortfolioMLDirectNumericRequest,
    PortfolioMLDirectNumericStoreBuilder,
)
from data_module.portfolio_ml_raw_to_ooc_pipeline import (
    PortfolioMLRawToOOCRequest,
    PortfolioMLRawToOOCBuilder,
)
from data_module.ml_research_direct_ooc_adapter import (
    ResearchAdaptRequest,
    ResearchDirectOOCAdapter,
    ResearchDirectNumericStoreConsumer,
)
import data_module.ml_research_direct_ooc_adapter as adapter_module
import data_module.ml_revision_aware_raw_candidate as raw_module
from data_module.ml_research_output_boundary import resolve_ml_research_output_path
from data_module.ml_storage_capacity import StorageCapacityError
import data_module.ml_pit_year_shard_exporter as pit_exporter_module
import data_module.portfolio_ml_direct_numeric_store as direct_store_module
import data_module.portfolio_ml_raw_to_ooc_pipeline as raw_to_ooc_module


def _research(root: Path, *parts: str) -> Path:
    return root / "output" / "ml_research" / Path(*parts)


@pytest.fixture(autouse=True)
def _research_path_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def resolver(path: Path) -> Path:
        (tmp_path / "output" / "ml_research").mkdir(parents=True, exist_ok=True)
        return resolve_ml_research_output_path(path, repository_root=tmp_path)
    monkeypatch.setattr(adapter_module, "resolve_ml_research_output_path", resolver)
    monkeypatch.setattr(raw_module, "resolve_ml_research_output_path", resolver)
    monkeypatch.setattr(pit_exporter_module, "resolve_ml_research_output_path", resolver, raising=False)
    monkeypatch.setattr(direct_store_module, "resolve_ml_research_output_path", resolver, raising=False)
    monkeypatch.setattr(raw_to_ooc_module, "resolve_ml_research_output_path", resolver, raising=False)


def _snapshot_context(db_path: Path, root: Path, completed_at: str) -> tuple[Path, str]:
    db_stat = db_path.stat()
    payload = {
        "schema_version": "integration-consistent-sqlite-snapshot.v1",
        "status": "consistent_snapshot_created",
        "completed_at": completed_at,
        "source_database_path": "synthetic-source.sqlite",
        "source_observation": {
            "database": {
                "path": "synthetic-source.sqlite",
                "bytes": db_stat.st_size,
                "mtime_ns": db_stat.st_mtime_ns,
                "sha256": hashlib.sha256(db_path.read_bytes()).hexdigest(),
            },
            "revision_namespace_files": [],
            "source_generation_before": 0,
            "source_generation_after": 0,
        },
        "snapshot_quick_check": "ok",
        "source_and_revision_bytes_unchanged": True,
        "snapshot": {
            "path": str(db_path.resolve()),
            "bytes": db_stat.st_size,
            "mtime_ns": db_stat.st_mtime_ns,
            "sha256": hashlib.sha256(db_path.read_bytes()).hexdigest(),
        },
        "revision_custody_qualification": "requires_separate_strict_inspection",
    }
    receipt = root / "snapshot_receipt.json"
    receipt.write_text(json.dumps(payload), encoding="utf-8")
    return receipt, "sha256:" + hashlib.sha256(receipt.read_bytes()).hexdigest()


def _setup_synthetic_market_db(db_path: Path) -> None:
    """建立包含兩完整年度與市場行情的標準 SQLite 資料庫。"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    from tests.test_portfolio_ml_dataset_assembler import _database
    _database(db_path)
    with sqlite3.connect(db_path) as conn:
        daily_rows = conn.execute("SELECT * FROM daily_prices").fetchall()
        market_rows = conn.execute("SELECT * FROM market_indices").fetchall()
        # 複製並延伸至 2025 年，共 480 交易日
        conn.executemany(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(f"2025{str(r[0])[4:]}", *r[1:]) for r in daily_rows]
        )
        conn.executemany(
            "INSERT INTO market_indices VALUES (?, ?, ?, ?, ?, ?)",
            [(f"2025{str(r[0])[4:]}", *r[1:]) for r in market_rows]
        )
        conn.commit()


@pytest.mark.usefixtures("synthetic_ml_capacity")
def test_e2e_path_a_revision_aware_shards_to_direct_and_ooc(tmp_path: Path) -> None:
    """路徑 A：包含市場修訂的資料庫 -> allow_source_revision_research 產出 shards
    -> Direct Numeric Store (allow_research) -> Raw-to-OOC (allow_research)。
    """
    db_path = tmp_path / "sqlite" / "twstock.db"
    _setup_synthetic_market_db(db_path)

    # 1. 建立 raw year shards，開啟 allow_source_revision_research
    raw_root = _research(tmp_path, "raw_shards_candidate")
    exporter = PITYearShardExporter()
    req = PITYearShardBuildRequest(
        database_path=db_path,
        output_root=raw_root,
        decision_at="2026-01-01T08:30:00+08:00",
        history_start_date="2024-01-01",
        symbols=("2317", "2330"),
        years=(2024, 2025),
        allow_source_revision_research=True,
    )
    pub = exporter.build(req)

    # 驗證 Shards 產出具備研究屬性
    assert pub.dataset_manifest_paths
    all_field_manifest_path = pub.dataset_manifest_paths["all_field_enriched"]
    assert all_field_manifest_path.is_file()
    all_field_manifest = json.loads(all_field_manifest_path.read_text(encoding="utf-8"))

    assert all_field_manifest["safety"]["formal_dataset"] is False
    assert all_field_manifest["safety"]["research_only"] is True
    assert all_field_manifest["safety"]["formal_training_allowed"] is False
    assert all_field_manifest["safety"]["production_alpha_bp"] == 0

    # 2. 測試未帶 allow_research 的 Direct Store 會被 fail-closed 阻擋
    direct_root = _research(tmp_path, "direct_store_candidate")

    blocked_direct_req = PortfolioMLDirectNumericRequest(
        raw_manifest_path=all_field_manifest_path,
        output_root=direct_root,
        training_as_of="2026-01-01T08:30:00+08:00",
        benchmark_entity_id="TAIEX",
        corporate_action_manifest_path=None,
        minimum_train_dates=65,
        test_date_count=65,
        purge_trading_days=60,
        embargo_trading_days=5,
        allow_research=False,  # 未帶
    )
    with pytest.raises(ValueError, match="raw dataset is not formal|formal_dataset=true|research_only"):
        PortfolioMLDirectNumericStoreBuilder().build(blocked_direct_req)

    # 3. 帶入 allow_research=True 成功建立 Direct Numeric Store
    allowed_direct_req = PortfolioMLDirectNumericRequest(
        raw_manifest_path=all_field_manifest_path,
        output_root=direct_root,
        training_as_of="2026-01-01T08:30:00+08:00",
        benchmark_entity_id="TAIEX",
        corporate_action_manifest_path=None,
        minimum_train_dates=65,
        test_date_count=65,
        purge_trading_days=60,
        embargo_trading_days=5,
        allow_research=True,  # 帶入
    )
    direct_pub = PortfolioMLDirectNumericStoreBuilder().build(allowed_direct_req)

    assert direct_pub.manifest_path.is_file()
    direct_manifest = json.loads(direct_pub.manifest_path.read_text(encoding="utf-8"))
    assert direct_manifest["research_only"] is True
    assert direct_manifest["formal_source_only"] is False
    assert direct_manifest["safety"]["formal_oos_allowed"] is False
    assert direct_manifest["safety"]["production_alpha_bp"] == 0
    assert (direct_pub.run_directory / "checkpoint.json").is_file()
    assert direct_manifest["fold_qualification_policy"] == (
        "post_purge_distinct_train_dates.v1"
    )
    qualified_direct_folds = direct_manifest["folds"]
    assert len(qualified_direct_folds) == 4
    assert all(
        fold["train_date_count"] >= allowed_direct_req.minimum_train_dates
        for fold in qualified_direct_folds
    )

    # 4. 透過 Raw-to-OOC Pipeline 建立 OOC Store（帶入 allow_research=True）
    ooc_root = _research(tmp_path, "ooc_candidate")
    ooc_req = PortfolioMLRawToOOCRequest(
        raw_manifest_path=all_field_manifest_path,
        output_root=ooc_root,
        training_as_of="2026-01-01T08:30:00+08:00",
        benchmark_entity_id="TAIEX",
        corporate_action_manifest_path=None,
        minimum_train_dates=65,
        test_date_count=65,
        purge_trading_days=60,
        embargo_trading_days=5,
        years=(2024, 2025),
        allow_research=True,
    )
    ooc_pub = PortfolioMLRawToOOCBuilder().build(ooc_req)
    assert ooc_pub.training_manifest_path.is_file()
    ooc_manifest = json.loads(ooc_pub.training_manifest_path.read_text(encoding="utf-8"))
    assert ooc_manifest["research_only"] is True
    assert ooc_manifest["formal_source_only"] is False
    assert ooc_manifest["formal_oos_allowed"] is False
    assert ooc_manifest["minimum_train_dates"] == 65
    assert ooc_manifest["fold_qualification_policy"] == (
        "post_purge_distinct_train_dates.v1"
    )
    assert ooc_manifest["fold_count_semantics"] == (
        "candidate_windows_before_ooc_materialization"
    )
    assert ooc_manifest["fold_count"] == 5
    assert ooc_pub.store_publication.manifest_path.is_file()
    assert ooc_pub.store_publication.fold_count == 4
    ooc_store_manifest = json.loads(
        ooc_pub.store_publication.manifest_path.read_text(encoding="utf-8")
    )
    assert ooc_store_manifest["fold_qualification_policy"] == (
        "post_purge_distinct_train_dates.v1"
    )
    assert ooc_store_manifest["minimum_train_dates_after_purge"] == 65
    assert all(
        fold["train_date_count"] >= ooc_manifest["minimum_train_dates"]
        for fold in ooc_store_manifest["folds"]
    )
    assert ooc_pub.store_publication.row_count > 0


def test_e2e_path_b_adapter_and_consumer_full_chain(tmp_path: Path) -> None:
    """路徑 B：單日投影／候選資料 -> ResearchDirectOOCAdapter -> ResearchDirectNumericStoreConsumer。"""
    # 建立一個測試用的 daily projection jsonl
    proj_dir = tmp_path / "daily_projection"
    proj_dir.mkdir(parents=True, exist_ok=True)
    obs_file = proj_dir / "observations.jsonl"
    record1 = {
        "symbol": "2330",
        "source_date": "2026-09-30",
        "source_available_at": "2026-09-30T08:07:47+00:00",
        "exact_numeric_values": {
            "開盤價": {"value_int": 98000, "scale": 100},
            "最高價": {"value_int": 98500, "scale": 100},
            "最低價": {"value_int": 97500, "scale": 100},
            "收盤價": {"value_int": 98200, "scale": 100},
            "成交股數": {"value_int": 35000000, "scale": 1},
        },
        "source_raw_response_sha256": "",
        "source_receipt_sha256": "",
        "source_row_index": 0,
        "venue": "twse",
    }
    record2 = {
        "symbol": "2317",
        "source_date": "2026-09-30",
        "source_available_at": "2026-09-30T08:07:51+00:00",
        "exact_numeric_values": {
            "開盤價": {"value_int": 18500, "scale": 100},
            "最高價": {"value_int": 18700, "scale": 100},
            "最低價": {"value_int": 18300, "scale": 100},
            "收盤價": {"value_int": 18600, "scale": 100},
            "成交股數": {"value_int": 25000000, "scale": 1},
        },
        "source_raw_response_sha256": "",
        "source_receipt_sha256": "",
        "source_row_index": 1,
        "venue": "twse",
    }
    raw_path = proj_dir / "raw_response.bin"
    source_receipt_path = proj_dir / "source_receipt.json"
    raw_path.write_bytes(b"projection fixture raw")
    source_receipt_path.write_bytes(b"projection fixture receipt")
    raw_pin = "sha256:" + hashlib.sha256(raw_path.read_bytes()).hexdigest()
    source_pin = "sha256:" + hashlib.sha256(source_receipt_path.read_bytes()).hexdigest()
    for record in (record1, record2):
        record["source_raw_response_sha256"] = raw_pin
        record["source_receipt_sha256"] = source_pin
    with obs_file.open("w", encoding="utf-8") as f:
        f.write(json.dumps(record1) + "\n")
        f.write(json.dumps(record2) + "\n")

    daily_manifest_path = proj_dir / "manifest.json"
    obs_sha = "sha256:" + hashlib.sha256(obs_file.read_bytes()).hexdigest()
    daily_manifest_payload = {
        "schema_version": "ml-daily-source-row-research-projection.v1",
        "research_only": True,
        "formal_dataset": False,
        "observations_file": {"path": "observations.jsonl", "sha256": obs_sha, "bytes": obs_file.stat().st_size, "row_count": 2},
        "input_files": {
            "raw_response.bin": {"bytes": raw_path.stat().st_size, "sha256": raw_pin},
            "source_receipt.json": {"bytes": source_receipt_path.stat().st_size, "sha256": source_pin},
        },
    }
    canonical_manifest = json.dumps(daily_manifest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    daily_manifest_payload["content_sha256"] = "sha256:" + hashlib.sha256(canonical_manifest).hexdigest()
    manifest_bytes = json.dumps(daily_manifest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    daily_manifest_path.write_bytes(manifest_bytes)
    manifest_sha = "sha256:" + hashlib.sha256(manifest_bytes).hexdigest()
    (proj_dir / "completion_receipt.json").write_text(json.dumps({
        "schema_version": "ml-daily-source-row-research-completion.v1",
        "completion_status": "awaiting_terminal_revision_validation",
        "manifest_sha256": manifest_sha,
        "observations_sha256": obs_sha,
    }), encoding="utf-8")
    (proj_dir / "runner_terminal_verification_receipt.json").write_text(json.dumps({
        "schema_version": "ml-daily-source-row-runner-terminal-receipt.v1",
        "terminal_status": "completed_research_only",
        "historical_pit_eligible": False,
        "features_included": False,
        "labels_included": False,
        "projection": {"manifest_sha256": manifest_sha, "observations_sha256": obs_sha},
    }), encoding="utf-8")

    # 1. 執行適配器
    adapted_dir = _research(tmp_path, "adapted_dataset")
    adapt_req = ResearchAdaptRequest(
        raw_candidate_manifest_path=daily_manifest_path,
        output_dir=adapted_dir,
        training_as_of="2026-10-01T08:30:00+08:00",
        benchmark_entity_id="TAIEX",
        expected_candidate_manifest_bytes_sha256="sha256:" + hashlib.sha256(daily_manifest_path.read_bytes()).hexdigest(),
    )
    adapter = ResearchDirectOOCAdapter(adapt_req)
    result = adapter.adapt()

    assert result.status == "verified_numeric_observations_ready"
    assert result.row_count == 2
    assert result.formal_release_v4_pointer_untouched is True

    # 2. 執行研究 Direct Numeric Store Consumer
    store_dir = _research(tmp_path, "research_direct_store")
    consumer = ResearchDirectNumericStoreConsumer(
        adapter_receipt_path=result.adapter_receipt_path,
        output_store_dir=store_dir,
        training_as_of="2026-10-01T08:30:00+08:00",
        benchmark_entity_id="TAIEX",
    )
    store_receipt = consumer.build_store()

    assert store_receipt["status"] == "verified_numeric_observations_ready"
    assert store_receipt["record_count"] == 2
    assert store_receipt["formal_release_v4_pointer_untouched"] is True
    assert store_receipt["research_only"] is True

    # 驗證消費收據在磁碟上
    assert (store_dir / "consumption_receipt.json").is_file()
    assert (store_dir / "store_metadata.json").is_file()
    assert (store_dir / "feature_registry.json").is_file()
    assert store_receipt["direct_ooc_status"] == "blocked_insufficient_context_or_mature_history"


def test_isolation_defenses_prevent_release_v4_and_naked_float(tmp_path: Path) -> None:
    """驗證所有研究模式組件均嚴格禁止輸出至 release_v4，且嚴格拒絕裸 float。"""
    forbidden_target = tmp_path / "release_v4" / "leaked_candidate"

    # 測試適配器防護
    dummy_manifest = tmp_path / "dummy.json"
    dummy_manifest.write_text("{}", encoding="utf-8")
    with pytest.raises(Exception, match="ML research output"):
        ResearchAdaptRequest(
            raw_candidate_manifest_path=dummy_manifest,
            output_dir=forbidden_target,
            training_as_of="2026-10-01T08:30:00+08:00",
        )

    # 測試 Direct Store 輸出防護
    with pytest.raises(ValueError, match="ML research output"):
        PortfolioMLDirectNumericRequest(
            raw_manifest_path=dummy_manifest,
            output_root=forbidden_target,
            training_as_of="2026-10-01T08:30:00+08:00",
            benchmark_entity_id="TAIEX",
            allow_research=True,
        )

    # 測試 Raw-to-OOC 輸出防護
    with pytest.raises(ValueError, match="ML research output"):
        PortfolioMLRawToOOCRequest(
            raw_manifest_path=dummy_manifest,
            output_root=forbidden_target,
            training_as_of="2026-10-01T08:30:00+08:00",
            benchmark_entity_id="TAIEX",
            allow_research=True,
        )
