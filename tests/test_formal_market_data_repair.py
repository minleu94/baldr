"""正式市場修訂的來源、交易、原始資料保留與中斷恢復邊界。"""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sqlite3

import pytest

from scripts import repair_formal_market_data as repair
from data_module.formal_market_revision import RECEIPT_DIR, assert_market_revision_safe, validate_market_replacement
from data_module.ml_daily_price_revision_gate import check_daily_price_source_revision, DailyPriceSourceRevisionError
from data_module.ml_restatement_official_market import REPORT_FIELDS, REPORT_PATHS, file_sha256, parse_monthly_report


@pytest.fixture
def scenario(tmp_path: Path):
    source_dir = tmp_path / 'source'
    source_dir.mkdir()
    receipts, rows = [], {}
    for report, fields in REPORT_FIELDS.items():
        values = ['10,000', '20,000', '30', '103.00', '3.00'] if report == 'FMTQIK' else ['100.00', '105.00', '99.00', '103.00']
        payload = {'stat': 'OK', 'date': '20240101', 'fields': list(fields), 'data': [['113/01/02', *values], ['113/01/04', *values]]}
        path = source_dir / f'202401-{report}.json'
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        receipts.append({'file': path.name, 'report': report, 'month': '202401',
                         'url': f'https://www.twse.com.tw{REPORT_PATHS[report]}?date=20240101&response=json',
                         'captured_at': '2024-02-01T01:00:00+08:00', 'historical_pit': False,
                         'file_sha256': file_sha256(path), 'byte_count': path.stat().st_size})
        for day, values_by_name in parse_monthly_report(payload, report=report, month='202401').items():
            rows.setdefault(day.isoformat(), {}).update({k: str(v) for k, v in values_by_name.items()})
    manifest = {'schema_version': 'official-market-source-capture.v1', 'historical_pit': False,
                'source_db_write': False, 'failures': [], 'status': 'incomplete',
                'volume_unit': 'TWSE FMTQIK 成交股數（股）', 'ohlc_source': 'TWSE MI_5MINS_HIST',
                'started_at': '2024-02-01T00:00:00+08:00', 'finished_at': '2024-02-01T02:00:00+08:00',
                'cutoff_date': '2024-01-31', 'months': ['202401'], 'receipts': receipts,
                'rows': rows, 'row_count': 2, 'original_observed_dates_missing_official': ['2024-01-03'],
                'official_additional_dates': ['2024-01-04']}
    source = source_dir / 'capture.json'
    source.write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
    root = tmp_path / 'formal'
    (root / 'sqlite').mkdir(parents=True)
    db = root / 'sqlite/twstock.db'
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE market_indices (日期 TEXT, 指數名稱 TEXT, 收盤指數 REAL, 開盤價 REAL, 最高價 REAL, 最低價 REAL, 收盤價 REAL, 成交量 REAL, 漲跌點數 REAL, 漲跌百分比 REAL, 漲跌 TEXT, UNIQUE(日期,指數名稱))')
        c.executemany('INSERT INTO market_indices VALUES (?,?,1,1,1,1,1,2,NULL,NULL,NULL)', [('20240102', 'TAIEX'), ('20240103', 'TAIEX'), ('20240102', 'OTHER')])
        c.execute('CREATE TABLE unrelated (value TEXT)')
        c.execute("INSERT INTO unrelated VALUES ('keep')")
    csv_path = root / 'market_index.csv'
    csv_path.write_text('日期,開盤價,最高價,最低價,收盤價,成交量\n2024-01-02,1,1,1,1,2\n2024-01-03,1,1,1,1,2\n', encoding='utf-8-sig')
    original_csv = csv_path.read_bytes()
    plan = repair.build_plan(db, csv_path, [{'path': str(source), 'sha256': repair.file_hash(source)}])
    plan_path = tmp_path / 'plan.json'
    plan_path.write_bytes(repair.encoded(plan))
    directory = root / RECEIPT_DIR / 'run01'
    return db, csv_path, plan, plan_path, directory, original_csv


def perform(scenario):
    _, _, _, plan_path, directory, _ = scenario
    return repair.apply(plan_path, repair.file_hash(plan_path), directory, repair.CONFIRM)


def test_apply_source_exactness_non_targets_and_roundtrip(scenario):
    db, csv_path, plan, _, directory, original = scenario
    assert plan['summary']['remove_dates'] == ['20240103']
    assert plan['summary']['insert_dates'] == ['20240104']
    perform(scenario)
    with repair.readonly(db) as c:
        assert c.execute("SELECT 開盤價,最高價,最低價,收盤價,成交量 FROM market_indices WHERE 日期='20240102' AND 指數名稱='TAIEX'").fetchone() == (100, 105, 99, 103, 10000)
        assert c.execute("SELECT 收盤價 FROM market_indices WHERE 指數名稱='OTHER'").fetchone() == (1,)
        assert c.execute('SELECT * FROM unrelated').fetchone() == ('keep',)
    assert (directory / 'market_before.csv').read_bytes() == original
    with pytest.raises(ValueError, match='historical PIT'):
        assert_market_revision_safe(db, date(2024, 1, 2))
    with pytest.raises(DailyPriceSourceRevisionError, match='market source revision'):
        check_daily_price_source_revision(database_path=db, decision_date='2024-01-02', symbols=['1256'])
    assert_market_revision_safe(db, date(2024, 1, 1))
    repair.recover(directory, rollback=True, confirm=repair.CONFIRM)
    assert csv_path.read_bytes() == original
    with repair.readonly(db) as c:
        assert repair.normalized(repair.snapshot(c)) == plan['before']
    assert_market_revision_safe(db, date(2024, 1, 2))


@pytest.mark.parametrize('kind', ['source', 'plan', 'csv', 'database'])
def test_drift_rejected_before_any_formal_mutation(scenario, kind):
    db, csv_path, plan, plan_path, directory, _ = scenario
    if kind == 'source':
        Path(plan['sources'][0]['path']).write_text('{}', encoding='utf-8')
    elif kind == 'plan':
        plan['after']['rows'][0]['收盤價'] = '999'
        plan_path.write_bytes(repair.encoded(plan))
    elif kind == 'csv':
        csv_path.write_bytes(csv_path.read_bytes() + b'\n')
    else:
        with sqlite3.connect(db) as c:
            c.execute("UPDATE market_indices SET 收盤價=7 WHERE 指數名稱='OTHER'")
    before_csv = csv_path.read_bytes()
    with repair.readonly(db) as c:
        before = repair.snapshot(c)
    with pytest.raises(ValueError):
        perform(scenario)
    assert not directory.exists()
    assert csv_path.read_bytes() == before_csv
    with repair.readonly(db) as c:
        assert repair.snapshot(c) == before


@pytest.mark.parametrize('point', ['csv', 'receipt'])
def test_interrupted_publication_can_be_resumed(scenario, monkeypatch, point):
    db, csv_path, plan, _, directory, original = scenario
    actual = repair.atomic

    def interrupted(path, body):
        actual(path, body)
        if (point == 'csv' and path == csv_path and body != original) or (point == 'receipt' and path == directory / 'receipt.json'):
            raise RuntimeError('simulated interruption')

    monkeypatch.setattr(repair, 'atomic', interrupted)
    with pytest.raises(RuntimeError, match='interruption'):
        perform(scenario)
    if point == 'csv':
        assert csv_path.read_bytes() == original
    monkeypatch.setattr(repair, 'atomic', actual)
    result = repair.recover(directory, rollback=False, confirm=repair.CONFIRM)
    assert result['state'] == ('rolled_back' if point == 'csv' else 'applied')
    with repair.readonly(db) as c:
        assert repair.normalized(repair.snapshot(c)) == plan['before' if point == 'csv' else 'after']
    assert csv_path.read_bytes() == (original if point == 'csv' else plan['csv_after_text'].encode('utf-8-sig'))


def test_post_apply_drift_prevents_rollback(scenario):
    db, csv_path, _, _, directory, _ = scenario
    perform(scenario)
    with sqlite3.connect(db) as c:
        c.execute("UPDATE market_indices SET 收盤價=104 WHERE 指數名稱='TAIEX'")
    before = csv_path.read_bytes()
    with pytest.raises(ValueError, match='漂移'):
        repair.recover(directory, rollback=True, confirm=repair.CONFIRM)
    assert csv_path.read_bytes() == before


def test_market_reimport_and_missing_history_protection(scenario):
    db, _, plan, _, _, _ = scenario
    perform(scenario)
    rows = [r for r in plan['after']['rows'] if r['指數名稱'] == 'TAIEX']
    validate_market_replacement(db, rows, replace_all=True)
    with pytest.raises(ValueError, match='缺少'):
        validate_market_replacement(db, [{'日期':'20240102','指數名稱':'OTHER','收盤價':1}], replace_dates=True)
    with pytest.raises(ValueError):
        validate_market_replacement(db, [{'日期':'20240102','指數名稱':'TAIEX','收盤價':103}], replace_dates=True)
    with pytest.raises(ValueError, match='缺少'):
        validate_market_replacement(db, rows[:1], replace_all=True)
    bad = [{**rows[0], '成交量': 10}]
    with pytest.raises(ValueError, match='覆蓋'):
        validate_market_replacement(db, bad)
    with pytest.raises(ValueError, match='非交易日'):
        validate_market_replacement(db, [{**rows[0], '日期': '20240103'}])
    validate_market_replacement(db, [{'日期': '20240202', '收盤價': 120}])


def test_tampered_marker_cannot_shift_historical_hold(scenario):
    db, _, _, _, directory, _ = scenario
    perform(scenario)
    path = directory / 'revision.json'
    payload = json.loads(path.read_text(encoding='utf-8'))
    payload['source_start_date'] = '2099-01-01'
    path.write_bytes(repair.encoded(payload))
    with pytest.raises(ValueError, match='無法驗證'):
        assert_market_revision_safe(db, date(2024, 1, 2))


def test_disjoint_source_spans_rejected_before_plan_can_delete_gap(scenario, monkeypatch):
    from types import SimpleNamespace
    db, csv_path, plan, _, directory, _ = scenario
    source = Path(plan['sources'][0]['path'])
    source2 = source.with_name('march.json')
    source2.write_text(json.dumps({'months': ['202403']}), encoding='utf-8')
    captures = [SimpleNamespace(rows={date(2024, 1, 2): {'日期': '20240102'}}, cutoff_date=date(2024, 1, 31)),
                SimpleNamespace(rows={date(2024, 3, 1): {'日期': '20240301'}}, cutoff_date=date(2024, 3, 31))]
    monkeypatch.setattr(repair, 'load_official_market_capture', lambda *args, **kwargs: captures.pop(0))
    with pytest.raises(ValueError, match='月份不連續'):
        repair.build_plan(db, csv_path, [*plan['sources'], {'path': str(source2), 'sha256': 'x'}])
    assert not directory.exists()
