"""Windows 長路徑下 run 原子保存、strict 讀回與索引查詢驗證。"""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from app_module.daily_market_universe_producer import produce_daily_market_universe_run
from app_module.daily_market_universe_run import (
    DAILY_MARKET_UNIVERSE_RUN_MAX_SEGMENT_BYTES,
    DailyMarketUniverseRunError,
    DailyMarketUniverseRunReader,
    _atomic_write_new,
    _hash_file,
    _read_json_limited,
    list_completed_runs,
)
from app_module.personal_data_paths import to_internal_io_path
from tests.test_daily_market_universe_managed_scope import _managed_request


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(to_internal_io_path(path), "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def test_managed_run_long_path_write_read_query_fresh_process_and_hash_guards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, producer_failures = _managed_request(tmp_path, monkeypatch)
    database = Path(request.db_path)
    database_before = (database.read_bytes(), database.stat().st_mtime_ns)

    result = produce_daily_market_universe_run(request)
    assert result.status == "complete", (result.error_code, result.cause_code)
    assert result.generation_identity_sha256 is not None
    assert not producer_failures
    assert result.counts["processed_count"] == 17
    assert (database.read_bytes(), database.stat().st_mtime_ns) == database_before

    output_root = Path(request.output_root)
    generation_id = result.generation_identity_sha256
    with DailyMarketUniverseRunReader.open(output_root, generation_id) as reader:
        first_page = reader.query(page=0, page_size=5, sort_key="stock_code")
        second_page = reader.query(page=1, page_size=5, sort_key="stock_code")
        assert first_page.total_count == first_page.filtered_count == 17
        assert len(first_page.rows) == len(second_page.rows) == 5
        assert first_page.rows[0]["stock_code"] != second_page.rows[0]["stock_code"]
        assert reader.counts["processed_count"] == 17
        segment = reader.manifest["segments"][0]
        projection_path = reader.run_root / segment["projection_relpath"]
        projection_sha = segment["projection_sha256"]

    assert len(str(projection_path)) > 260
    projection_raw, _projection = _read_json_limited(
        projection_path, DAILY_MARKET_UNIVERSE_RUN_MAX_SEGMENT_BYTES
    )
    assert hashlib.sha256(projection_raw).hexdigest() == projection_sha

    listed = list_completed_runs(output_root)
    assert [item.generation_identity_sha256 for item in listed.items] == [generation_id]
    assert listed.items[0].status == "complete"

    parent_reference = result.parent_references[0]
    script = (
        "import json,sys; from pathlib import Path; "
        "from app_module.daily_market_universe_run import DailyMarketUniverseRunReader,list_completed_runs; "
        "from app_module.rule_research_parent_capture import read_parent_rule_sample_readiness; "
        "r=DailyMarketUniverseRunReader.open(Path(sys.argv[1]),sys.argv[2]); "
        "q=r.query(page_size=25); runs=list_completed_runs(Path(sys.argv[1])); "
        "p=read_parent_rule_sample_readiness(sys.argv[3],sys.argv[4],"
        "universe_path=sys.argv[5],identity_sha256=sys.argv[6]); "
        "print(json.dumps({'count':q.total_count,'run_count':len(runs.items),"
        "'parent':p['status']})); r.close()"
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(output_root),
            generation_id,
            str(parent_reference.snapshot_root),
            str(parent_reference.capture_root),
            str(parent_reference.universe_path),
            parent_reference.capture_identity_sha256,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=40,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "count": 17,
        "run_count": 1,
        "parent": "saved_verified_complete",
    }

    before_digest, _before_size = _hash_file(
        projection_path, DAILY_MARKET_UNIVERSE_RUN_MAX_SEGMENT_BYTES
    )
    with pytest.raises(DailyMarketUniverseRunError) as immutable_error:
        _atomic_write_new(projection_path, b"immutable overwrite attempt")
    assert immutable_error.value.code == "immutable_run_file_exists"
    assert _hash_file(projection_path, DAILY_MARKET_UNIVERSE_RUN_MAX_SEGMENT_BYTES)[0] == before_digest

    with open(to_internal_io_path(projection_path), "wb") as handle:
        handle.write(projection_raw + b" ")
    try:
        with pytest.raises(DailyMarketUniverseRunError) as tamper_error:
            DailyMarketUniverseRunReader.open(output_root, generation_id)
        assert tamper_error.value.code == "segment_projection_hash_mismatch"
    finally:
        with open(to_internal_io_path(projection_path), "wb") as handle:
            handle.write(projection_raw)
    assert _sha256_file(projection_path) == before_digest
