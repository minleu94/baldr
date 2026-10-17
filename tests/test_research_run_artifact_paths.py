"""保存索引不得在搬移後沿用舊根或其他 run 的結果檔。"""

from dataclasses import asdict
from pathlib import Path
import json
import os
import shutil
import sqlite3
import subprocess
import sys

import pandas as pd
import pytest

from app_module.research_run_dtos import ResearchRunMetadataDTO
from app_module.research_run_service import ResearchRunIntegrityError, ResearchRunService
from data_module.config import TWStockConfig


def _service(root):
    return ResearchRunService(TWStockConfig(data_root=root / "data", output_root=root / "output"))


def _saved(service):
    return service.save_run(
        ResearchRunMetadataDTO(run_id="original", run_name="原研究", run_type="single_backtest",
                               payload_hash="sha256:original"),
        pd.DataFrame({"日期": ["2026-01-02"], "portfolio_value": [1000000]}),
        pd.DataFrame({"stock_code": ["2330"], "quantity": [1000]}),
    )


def _change_path(service, field, value):
    assert field in {"equity_path", "trades_path"}
    with sqlite3.connect(service.config.research_run_db_file) as connection:
        connection.execute(f"UPDATE research_runs SET {field}=? WHERE run_id='original'", (value,))


@pytest.mark.parametrize("copy_artifacts", [False, True])
def test_copied_index_cannot_silently_read_old_root(tmp_path, copy_artifacts):
    origin, destination = _service(tmp_path / "origin"), _service(tmp_path / "destination")
    saved = _saved(origin)
    before = {path: path.read_bytes() for path in (origin.repository.db_path, Path(saved.equity_path), Path(saved.trades_path))}
    destination.repository.db_path.parent.mkdir(parents=True, exist_ok=True)
    assert not destination.repository.db_path.exists()
    shutil.copyfile(origin.repository.db_path, destination.repository.db_path)
    if copy_artifacts:
        destination.parquet_dir.mkdir(parents=True, exist_ok=True)
        for path in (Path(saved.equity_path), Path(saved.trades_path)):
            shutil.copyfile(path, destination.parquet_dir / path.name)

    # 原檔仍在且 SHA 正確，也不可把它當作新根的搬移成果。
    with pytest.raises(ResearchRunIntegrityError, match="保存檔案路徑"):
        destination.load_run_data(saved.run_id)
    assert {path: path.read_bytes() for path in before} == before
    assert origin.load_run_data(saved.run_id).equity.iloc[0]["portfolio_value"] == 1000000


@pytest.mark.parametrize("field", ["equity_path", "trades_path"])
@pytest.mark.parametrize("kind", ["relative", "sibling", "outside"])
def test_metadata_must_point_to_this_run_final_artifact(tmp_path, field, kind):
    service = _service(tmp_path)
    saved = _saved(service)
    source = Path(getattr(saved, field))
    if kind == "relative":
        value = source.name
    else:
        other = (service.parquet_dir if kind == "sibling" else tmp_path) / ("other_" + source.name)
        shutil.copyfile(source, other)
        value = str(other)
    _change_path(service, field, value)
    with pytest.raises(ResearchRunIntegrityError, match="保存檔案路徑"):
        service.load_run_data(saved.run_id)


@pytest.mark.parametrize("field", ["equity_path", "trades_path"])
@pytest.mark.parametrize("target_kind", ["file", "directory"])
def test_reparse_artifact_rejected_before_parquet_decode(tmp_path, monkeypatch, field, target_kind):
    service = _service(tmp_path)
    saved = _saved(service)
    target = Path(getattr(saved, field)) if target_kind == "file" else service.parquet_dir
    original = service._is_symlink_or_reparse_point
    monkeypatch.setattr(service, "_is_symlink_or_reparse_point", lambda path: path == target or original(path))
    monkeypatch.setattr(pd, "read_parquet", lambda *args, **kwargs: pytest.fail("路徑核對前不可解碼 Parquet"))
    with pytest.raises(ResearchRunIntegrityError, match="保存檔案路徑"):
        service.load_run_data(saved.run_id)


def test_same_root_new_service_preserves_exact_saved_result(tmp_path):
    service = _service(tmp_path)
    saved = _saved(service)
    loaded = _service(tmp_path).load_run_data(saved.run_id)
    assert loaded.metadata == saved
    assert loaded.equity.to_dict("list") == {"日期": ["2026-01-02"], "portfolio_value": [1000000]}
    assert loaded.trades.to_dict("list") == {"stock_code": ["2330"], "quantity": [1000]}


def test_saved_result_reopens_in_new_process_without_rewriting_source(tmp_path):
    service = _service(tmp_path)
    saved = _saved(service)
    before = {path: path.read_bytes() for path in (service.repository.db_path, Path(saved.equity_path), Path(saved.trades_path))}
    code = """
from dataclasses import asdict
import json
from pathlib import Path
import sys
from app_module.research_run_service import ResearchRunService
from data_module.config import TWStockConfig
root = Path(sys.argv[1])
loaded = ResearchRunService(TWStockConfig(data_root=root/'data', output_root=root/'output')).load_run_data('original')
print(json.dumps({'pid': __import__('os').getpid(), 'metadata': asdict(loaded.metadata),
                  'equity': loaded.equity.to_dict('list'), 'trades': loaded.trades.to_dict('list')}))
"""
    completed = subprocess.run([sys.executable, "-X", "utf8", "-B", "-c", code, str(tmp_path)],
                               capture_output=True, text=True, check=True, timeout=30)
    result = json.loads(completed.stdout.splitlines()[-1])
    assert result["pid"] != os.getpid()
    assert result["metadata"] == asdict(saved)
    assert result["equity"] == {"日期": ["2026-01-02"], "portfolio_value": [1000000]}
    assert result["trades"] == {"stock_code": ["2330"], "quantity": [1000]}
    assert {path: path.read_bytes() for path in before} == before


def test_history_public_reader_propagates_path_rejection(tmp_path):
    from app_module.research_history_lookup import ResearchHistoryLookup, ResearchHistoryReadBudget

    service = _service(tmp_path)
    saved = _saved(service)
    lookup = ResearchHistoryLookup(registry=service, read_budget=ResearchHistoryReadBudget(1024 * 1024, 2 * 1024 * 1024))
    _change_path(service, "equity_path", str(tmp_path / "outside.parquet"))
    # 明選修改後同一筆，確保觸發的是路徑守衛而非舊選取漂移。
    selected = lookup.select_registry_run(saved.run_id)
    with pytest.raises(ResearchRunIntegrityError, match="保存檔案路徑"):
        lookup.resolve(selected)
