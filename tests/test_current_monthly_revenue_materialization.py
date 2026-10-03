"""月營收原件綁定、Decimal正規化及現況限定寫入。"""
from pathlib import Path
import sqlite3

import pytest

from data_module.current_monthly_revenue_materialization import plan_current_revenue, apply_current_revenue
from data_module.monthly_revenue_snapshot_harvester import (
    _snapshot_source_version, parse_mops_monthly_revenue_snapshot_html, write_mops_snapshot_csv,
)


def snapshot(tmp_path: Path, *, unit: str = '千元') -> Path:
    raw_dir = tmp_path / 'raw_html'
    raw_dir.mkdir()
    headers = ['公司代號', '公司名稱', '當月營收', '上月營收', '去年當月營收', '當月累計營收', '去年累計營收']
    rows = []
    for market, code, title in [('twse','2330','上市'), ('tpex','6488','上櫃')]:
        html = f'<h1>{title}公司115年8月份</h1><p>單位：{unit}</p><table><tr>' + ''.join(f'<th>{h}</th>' for h in headers) + '</tr><tr>' + ''.join(f'<td>{v}</td>' for v in [code,'公司','1,234.5','1000','900','10000','9000']) + '</tr></table>'
        (raw_dir / f'{market}_2026-08.html').write_text(html, encoding='utf-8-sig')
        parsed, diagnostics = parse_mops_monthly_revenue_snapshot_html(html, market=market, period='2026-08', fetched_at='2026-09-11T00:00:00Z', source_version=_snapshot_source_version(market=market, period='2026-08', html=html))
        assert not diagnostics
        rows.extend(parsed)
    path = tmp_path / 'snapshot.csv'
    write_mops_snapshot_csv(path, rows)
    return path


def test_complete_normalization_uses_verified_clock_and_decimal(tmp_path):
    plan = plan_current_revenue(snapshot(tmp_path))
    assert len(plan.records) == 2
    assert plan.records[0]['value'] == '1234500.0'
    assert plan.records[0]['observed_at'] > '2026-09-11T00:00:00'
    assert plan.custody['formal_pit_eligible'] is False


def test_unknown_unit_cannot_be_promoted(tmp_path):
    with pytest.raises(ValueError, match='不能猜測'):
        plan_current_revenue(snapshot(tmp_path, unit='未知'))


def test_changed_csv_rejected(tmp_path):
    path = snapshot(tmp_path)
    path.write_text(path.read_text(encoding='utf-8-sig').replace('1234.5', '2345.6'), encoding='utf-8-sig')
    with pytest.raises(ValueError, match='逐列'):
        plan_current_revenue(path)


def test_wrong_raw_period_rejected(tmp_path):
    path = snapshot(tmp_path)
    raw = tmp_path / 'raw_html/twse_2026-08.html'
    raw.write_text(raw.read_text(encoding='utf-8-sig').replace('8月份', '7月份'), encoding='utf-8-sig')
    with pytest.raises(ValueError, match='期別不符'):
        plan_current_revenue(path)


def test_append_is_idempotent_and_formal_table_unchanged(tmp_path):
    path = snapshot(tmp_path)
    db = tmp_path / 'data.db'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE fundamental_monthly_revenues(value TEXT)')
        conn.execute("INSERT INTO fundamental_monthly_revenues VALUES ('original')")
    first = apply_current_revenue(plan_current_revenue(path), db_file=db, backup_dir=tmp_path/'backup', receipt_dir=tmp_path/'receipts')
    with sqlite3.connect(db) as conn:
        before = conn.execute('SELECT * FROM fundamental_current_observations ORDER BY stock_code').fetchall()
    second = apply_current_revenue(plan_current_revenue(path), db_file=db, backup_dir=tmp_path/'backup', receipt_dir=tmp_path/'receipts')
    assert first['inserted_count'] == 2 and second['inserted_count'] == 0
    assert Path(first['backup_file']).exists()
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT * FROM fundamental_monthly_revenues').fetchall() == [('original',)]
        assert conn.execute('SELECT * FROM fundamental_current_observations ORDER BY stock_code').fetchall() == before
