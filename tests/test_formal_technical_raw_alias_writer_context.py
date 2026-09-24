from __future__ import annotations

import os
from pathlib import Path
import runpy
import sqlite3

import pandas as pd
import pytest

from data_module import formal_technical_raw_alias_repair as repair


_FIXTURES = runpy.run_path(
    str(Path(__file__).with_name("test_formal_technical_raw_alias_repair.py"))
)


def _applied_context(tmp_path: Path):
    fixture = _FIXTURES["_fixture"]
    apply_marker = _FIXTURES["_apply_raw_alias_marker"]
    root, technical_receipt, raw_receipt, _ = fixture(tmp_path)
    database_path = apply_marker(root, technical_receipt, raw_receipt)
    context = repair.create_raw_alias_writer_context(database_path)
    assert context is not None
    return database_path, context


def test_writer_context_reuses_verified_parse_but_hashes_current_bytes(tmp_path: Path, monkeypatch) -> None:
    database_path, context = _applied_context(tmp_path)
    assert context.cache_hits == 0

    def parsing_again(_path: Path):
        raise AssertionError("同一次 writer scope 不應重新 parse 已核驗 metadata")

    monkeypatch.setattr(repair, "_read_json_bytes", parsing_again)
    source_db = context.ensure_current(database_path)
    assert source_db == context.source_db
    assert context.cache_hits == 1


def test_writer_context_rejects_same_size_same_mtime_receipt_mutation(tmp_path: Path) -> None:
    database_path, context = _applied_context(tmp_path)
    receipt_path = next(
        path
        for path, _ in context.metadata_hashes
        if path.parent.parent == context.receipt_root and path.name == "receipt.json"
    )
    before = receipt_path.stat()
    original = receipt_path.read_bytes()
    changed = original.replace(b'"state":"applied"', b'"state":"applieD"', 1)
    assert changed != original and len(changed) == len(original)

    receipt_path.write_bytes(changed)
    os.utime(receipt_path, ns=(before.st_atime_ns, before.st_mtime_ns))
    after = receipt_path.stat()
    assert after.st_size == before.st_size
    assert after.st_mtime_ns == before.st_mtime_ns
    with pytest.raises(repair.RawAliasRepairError, match="raw alias evidence bytes"):
        context.ensure_current(database_path)


def test_writer_context_rejects_source_identity_change_and_wrong_database(tmp_path: Path) -> None:
    database_path, context = _applied_context(tmp_path / "first")
    other_database_path, other_context = _applied_context(tmp_path / "second")
    assert context is not other_context
    assert context.cache_hits == 0
    assert other_context.cache_hits == 0

    with pytest.raises(repair.RawAliasRepairError, match="SQLite 路徑不同"):
        context.ensure_current(other_database_path)
    with pytest.raises(repair.RawAliasRepairError, match="SQLite 路徑不同"):
        repair.validate_raw_alias_replacement(
            other_database_path,
            [],
            writer_context=context,
        )

    with context.source_db.open("ab") as stream:
        stream.write(b"x")
    with pytest.raises(repair.RawAliasRepairError, match="source 檔案身分"):
        context.ensure_current(database_path)
    assert other_context.cache_hits == 0


def test_writer_context_is_reloaded_for_each_run_on_the_same_database(tmp_path: Path) -> None:
    database_path, first_context = _applied_context(tmp_path)
    second_context = repair.create_raw_alias_writer_context(database_path)
    assert second_context is not None
    assert second_context is not first_context
    assert first_context.cache_hits == 0
    assert second_context.cache_hits == 0

    first_context.ensure_current(database_path)
    assert first_context.cache_hits == 1
    assert second_context.cache_hits == 0
    second_context.ensure_current(database_path)
    assert second_context.cache_hits == 1


@pytest.mark.parametrize("state", ["pending", "rolled_back"])
def test_writer_context_rejects_apply_or_rollback_state_drift(
    tmp_path: Path,
    state: str,
) -> None:
    database_path, context = _applied_context(tmp_path)
    journal_path = context.receipt_root / context.receipt_entries[0] / "journal.json"
    journal = repair._read_sealed(journal_path)
    journal["state"] = state
    repair._write_sealed(journal_path, journal)

    with pytest.raises(repair.RawAliasRepairError, match="evidence bytes"):
        context.ensure_current(database_path)


def test_writer_context_rejects_new_pending_run_inventory(tmp_path: Path) -> None:
    database_path, context = _applied_context(tmp_path)
    new_run = context.receipt_root / "run02"
    new_run.mkdir()
    repair._write_sealed(new_run / "journal.json", {"state": "pending"})

    with pytest.raises(repair.RawAliasRepairError, match="receipt inventory"):
        context.ensure_current(database_path)


def test_unapplied_root_does_not_create_writer_context(tmp_path: Path) -> None:
    fixture = _FIXTURES["_fixture"]
    root, _technical_receipt, _raw_receipt, _ = fixture(tmp_path)
    database_path = root / "sqlite" / "twstock.db"
    assert repair.create_raw_alias_writer_context(database_path) is None


def test_publication_gate_detects_marker_added_after_update_preflight(tmp_path: Path) -> None:
    fixture = _FIXTURES["_fixture"]
    apply_marker = _FIXTURES["_apply_raw_alias_marker"]
    root, technical_receipt, raw_receipt, _ = fixture(tmp_path)
    database_path = root / "sqlite" / "twstock.db"
    assert repair.create_raw_alias_writer_context(database_path) is None

    # 模擬計算起始 preflight 後才有 applied marker 的並行情況。
    apply_marker(root, technical_receipt, raw_receipt)
    with repair._readonly(database_path) as connection:
        before = repair._table_fingerprint(connection, "technical_indicators")
        row = connection.execute(
            'SELECT 日期,證券代號,"最後揭示買價","最後揭示買量",'
            '"最後揭示賣價","最後揭示賣量",本益比,漲跌價差,MA5 '
            'FROM technical_indicators ORDER BY 證券代號,日期 LIMIT 1'
        ).fetchone()
    assert row is not None
    frame = pd.DataFrame(
        [row],
        columns=["日期", "證券代號", *repair.ALIASES, "MA5"],
    )
    frame.loc[0, "最後揭示買價"] = 999.0

    from app_module.update_service import _write_technical_indicator_publications

    with sqlite3.connect(database_path) as connection:
        with pytest.raises(repair.RawAliasRepairError, match="舊來源會覆寫"):
            _write_technical_indicator_publications(
                connection,
                frame,
                database_path=database_path,
                raw_alias_prevalidated=True,
                raw_alias_context=None,
            )

    with repair._readonly(database_path) as connection:
        assert repair._table_fingerprint(connection, "technical_indicators") == before


def test_final_schema_preflight_rejects_new_marker_before_ensure_columns(tmp_path: Path) -> None:
    fixture = _FIXTURES["_fixture"]
    apply_marker = _FIXTURES["_apply_raw_alias_marker"]
    root, technical_receipt, raw_receipt, _ = fixture(tmp_path)
    database_path = root / "sqlite" / "twstock.db"
    assert repair.create_raw_alias_writer_context(database_path) is None
    apply_marker(root, technical_receipt, raw_receipt)

    with repair._readonly(database_path) as connection:
        row = connection.execute(
            'SELECT 日期,證券代號,"最後揭示買價","最後揭示買量",'
            '"最後揭示賣價","最後揭示賣量",本益比,漲跌價差,MA5 '
            'FROM technical_indicators ORDER BY 證券代號,日期 LIMIT 1'
        ).fetchone()
    assert row is not None
    frame = pd.DataFrame(
        [row],
        columns=["日期", "證券代號", *repair.ALIASES, "MA5"],
    )
    frame.loc[0, "最後揭示買價"] = 999.0

    class SchemaSpy:
        db_path = database_path

        def __init__(self):
            self.ensure_columns_calls = 0

        def ensure_columns(self, _table, _columns):
            self.ensure_columns_calls += 1

    from app_module.update_service import (
        _preflight_and_ensure_technical_indicator_schema,
    )

    schema_spy = SchemaSpy()
    with pytest.raises(repair.RawAliasRepairError, match="舊來源會覆寫"):
        _preflight_and_ensure_technical_indicator_schema(
            schema_spy,
            frame,
            replace_all=False,
            raw_alias_context=None,
        )
    assert schema_spy.ensure_columns_calls == 0
