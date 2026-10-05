"""月營收原件綁定、Decimal正規化及現況限定寫入。"""
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3

import pytest

from data_module.current_monthly_revenue_materialization import plan_current_revenue, apply_current_revenue
from data_module.current_fundamental_snapshots import (
    ensure_current_observation_schema,
    insert_observations,
)
from data_module.monthly_revenue_snapshot_harvester import (
    _snapshot_source_version, parse_mops_monthly_revenue_snapshot_html, write_mops_snapshot_csv,
)


def snapshot(tmp_path: Path, *, unit: str = '\u5343\u5143', captured_at: str | None = None) -> Path:
    raw_dir = tmp_path / 'raw_html'
    raw_dir.mkdir()
    headers = ['公司代號', '公司名稱', '當月營收', '上月營收', '去年當月營收', '當月累計營收', '去年累計營收']
    rows = []
    for market, code, title in [('twse','2330','上市'), ('tpex','6488','上櫃')]:
        html = f'<h1>{title}公司115年8月份</h1><p>單位：{unit}</p><table><tr>' + ''.join(f'<th>{h}</th>' for h in headers) + '</tr><tr>' + ''.join(f'<td>{v}</td>' for v in [code,'公司','1,234.5','1000','900','10000','9000']) + '</tr></table>'
        (raw_dir / f'{market}_2026-08.html').write_text(html, encoding='utf-8-sig')
        fetched_at = captured_at or '2026-09-11T00:00:00Z'
        parsed, diagnostics = parse_mops_monthly_revenue_snapshot_html(html, market=market, period='2026-08', fetched_at=fetched_at, source_version=_snapshot_source_version(market=market, period='2026-08', html=html, captured_at=captured_at))
        assert not diagnostics
        rows.extend(parsed)
    path = tmp_path / 'snapshot.csv'
    write_mops_snapshot_csv(path, rows)
    return path


def test_complete_normalization_uses_verified_clock_and_decimal(tmp_path):
    plan = plan_current_revenue(snapshot(tmp_path))
    assert len(plan.records) == 4
    assert plan.records[0]['value'] == '1234500.0'
    assert plan.records[0]['observed_at'] > '2026-09-11T00:00:00'
    assert all(row['period_basis'] == 'monthly_flow' for row in plan.records)
    assert all(row['basis_verified'] == '1' for row in plan.records)
    assert all(row['aggregate_feature_eligible'] == '0' for row in plan.records)
    revenue_rows = [row for row in plan.records if row['item_code'] == 'revenue']
    comparator_rows = [row for row in plan.records if row['item_code'] == 'revenue_yoy_comparator']
    assert len(revenue_rows) == len(comparator_rows) == 2
    assert all('mops-current-revenue-normalizer.v2:' in row['source_version'] for row in revenue_rows)
    assert all('mops-current-revenue-yoy-comparator.v1:' in row['source_version'] for row in comparator_rows)
    assert all(row['period'] == '2025-08' and row['value'] == '900000' for row in comparator_rows)
    assert all(row['unit'] == 'TWD' and row['formal_pit_eligible'] is False for row in plan.records if 'formal_pit_eligible' in row)
    assert all(row['period_basis'] == 'monthly_flow' and row['basis_verified'] == '1' for row in comparator_rows)
    assert all(row['aggregate_feature_eligible'] == '0' for row in comparator_rows)
    assert all(row['observed_at'] == revenue_rows[index]['observed_at'] for index, row in enumerate(comparator_rows))
    assert all(':raw:mops-static-' in row['source_version'] for row in revenue_rows)
    assert all(row['source_available_at']=='' for row in plan.records)
    assert all(row['observed_at'] > '2026-09-11T00:00:00' for row in plan.records)
    assert plan.custody['formal_pit_eligible'] is False
    assert plan.custody['normalization_version'] == 'mops-current-revenue-normalizer.v2'
    assert plan.custody['aggregate_feature_eligible'] is False


def test_v2_monthly_capture_keeps_proven_body_completion_clock(tmp_path):
    capture_time = '2026-10-04T00:01:02.123456Z'
    plan = plan_current_revenue(snapshot(tmp_path, captured_at=capture_time))
    assert all(row['source_available_at'] == '2026-10-04T00:01:02.123456+00:00' for row in plan.records)
    assert all(row['source_available_at'] < row['observed_at'] for row in plan.records)
    assert all('body_completed_at:2026-10-04T00:01:02.123456+00:00' in row['source_version'] for row in plan.records)


def test_late_comparator_append_keeps_its_actual_observation_clock(tmp_path):
    plan = plan_current_revenue(snapshot(tmp_path))
    database = tmp_path / 'clock-binding.db'
    revenue_rows = [row for row in plan.records if row['item_code'] == 'revenue']
    comparator_rows = [dict(row) for row in plan.records if row['item_code'] == 'revenue_yoy_comparator']
    for row in comparator_rows:
        row['observed_at'] = (
            datetime.fromisoformat(row['observed_at']) + timedelta(seconds=1)
        ).isoformat()
    with sqlite3.connect(database) as connection:
        ensure_current_observation_schema(connection)
        assert insert_observations(connection, revenue_rows) == len(revenue_rows)
        assert insert_observations(connection, comparator_rows) == len(comparator_rows)
        clocks = connection.execute(
            "SELECT item_code, observed_at FROM fundamental_current_observations "
            "WHERE stock_code='2330' ORDER BY item_code"
        ).fetchall()
    assert len(clocks) == 2
    assert clocks[0][1] != clocks[1][1]
    assert clocks[1][1] > clocks[0][1]


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
    assert first['inserted_count'] == 4 and second['inserted_count'] == 0
    assert Path(first['backup_file']).exists()
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT * FROM fundamental_monthly_revenues').fetchall() == [('original',)]
        assert conn.execute('SELECT * FROM fundamental_current_observations ORDER BY stock_code').fetchall() == before


def test_reverification_appends_normalizer_v2_beside_legacy_raw_source_version(tmp_path):
    plan = plan_current_revenue(snapshot(tmp_path))
    record = next(row for row in plan.records if row['stock_code'] == '2330')
    derived_version = record['source_version']
    raw_version = derived_version.split(':raw:', 1)[1].split(':derived:', 1)[0]
    legacy = {key: value for key, value in record.items() if key not in {
        'period_basis', 'basis_verified', 'aggregate_feature_eligible'
    }}
    legacy['source_version'] = raw_version
    legacy['observed_at'] = '2026-09-11T00:00:00+00:00'

    connection = sqlite3.connect(tmp_path / 'legacy-current.db')
    connection.execute(
        """CREATE TABLE fundamental_current_observations (
        stock_code TEXT NOT NULL, kind TEXT NOT NULL, period TEXT NOT NULL,
        as_of_date TEXT NOT NULL, item_code TEXT NOT NULL, item_name TEXT NOT NULL,
        value TEXT NOT NULL, unit TEXT NOT NULL, observed_at TEXT NOT NULL,
        source TEXT NOT NULL, source_version TEXT NOT NULL, market TEXT NOT NULL,
        PRIMARY KEY(stock_code, kind, period, item_code, source_version))"""
    )
    columns = (
        'stock_code', 'kind', 'period', 'as_of_date', 'item_code', 'item_name',
        'value', 'unit', 'observed_at', 'source', 'source_version', 'market',
    )
    connection.execute(
        f"INSERT INTO fundamental_current_observations ({','.join(columns)}) "
        f"VALUES ({','.join('?' for _ in columns)})",
        tuple(legacy[column] for column in columns),
    )
    connection.commit()
    connection.close()

    # 原始來源版本既有列不可更新；升版以正規化版本另追加一列。
    assert apply_current_revenue(
        plan,
        db_file=tmp_path / 'legacy-current.db',
        backup_dir=tmp_path / 'legacy-backups',
        receipt_dir=tmp_path / 'legacy-receipts',
    )['inserted_count'] == 4
    with sqlite3.connect(tmp_path / 'legacy-current.db') as connection:
        old, revised = connection.execute(
        "SELECT source_version,period_basis,basis_verified,aggregate_feature_eligible "
        "FROM fundamental_current_observations WHERE stock_code='2330' AND item_code='revenue' "
        "ORDER BY CASE WHEN source_version=? THEN 0 ELSE 1 END",
        (raw_version,),
        ).fetchall()
        assert old == (raw_version, 'unknown', 0, 0)
        assert revised == (derived_version, 'monthly_flow', 1, 0)
        assert connection.execute(
            "SELECT COUNT(*) FROM fundamental_current_observations WHERE stock_code='2330'"
        ).fetchone()[0] == 3
