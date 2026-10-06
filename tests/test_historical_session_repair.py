"""補回整日缺漏需雙市場來源，保留缺價並能回復中斷。"""
from datetime import date
import json
from pathlib import Path
import sqlite3

import pytest

from data_module.historical_session_revision import assert_session_revision_safe, validate_session_replacement, RECEIPT_DIR
from scripts import repair_historical_sessions as repair
from scripts.repair_historical_price_spike_20260921 import CANONICAL_COLUMNS


@pytest.fixture
def scenario(tmp_path):
    root = tmp_path / 'formal'
    (root / 'sqlite').mkdir(parents=True)
    db = root / 'sqlite/twstock.db'
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE daily_prices (' + ','.join('"' + k + '" ' + ('TEXT' if k in {'日期', '證券代號', '證券名稱', '漲跌'} else 'REAL') for k in repair.FIELDS) + ',extra TEXT, UNIQUE(日期,證券代號))')
        c.execute("INSERT INTO daily_prices (日期,證券代號,收盤價,extra) VALUES ('20141226','1256',99,'keep')")
        c.execute('CREATE TABLE technical_indicators (日期 TEXT, 證券代號 TEXT, RSI REAL)')
    sources = []
    day = '20141227'
    for venue in ('twse', 'tpex'):
        if venue == 'twse':
            table = {'fields': ['證券代號', *CANONICAL_COLUMNS], 'data': [['1256','測試甲','1,000','10','100,000','100','105','99','103','+','3','102','1','103','2','20']]}
            body = {'date': day, 'stat': 'OK', 'tables': [table]}
            url = f'https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={day}&type=ALLBUT0999&response=json'
        else:
            table = {'date': '103/12/27', 'fields': ['代號','名稱','成交股數','成交金額(元)','成交筆數','開盤','最高','最低','收盤','漲跌','最後買價','最後賣價'], 'data': [['5001','測試乙','0','0','0','---','---','---','20','---','19','20']]}
            body = {'date': day, 'stat': 'ok', 'tables': [table]}
            url = 'https://www.tpex.org.tw/www/zh-tw/afterTrading/otc?date=2014%2F12%2F27&type=EW&response=json'
        path = tmp_path / f'{venue}.json'
        path.write_bytes(repair.encoded(body))
        receipt = tmp_path / f'{venue}.receipt.json'
        receipt.write_bytes(repair.encoded({'date': day, 'url': url, 'captured_at': '2026-09-01T01:00:00+08:00', 'sha256': repair.file_hash(path), 'historical_pit': False}))
        sources.append({'path': str(path), 'receipt': str(receipt), 'sha256': repair.file_hash(path), 'receipt_sha256': repair.file_hash(receipt), 'day': day, 'venue': venue})
    plan = repair.build_plan(db, sources)
    plan_path = tmp_path / 'plan.json'
    plan_path.write_bytes(repair.encoded(plan))
    return db, plan, plan_path, root / RECEIPT_DIR / 'run01'


def perform(scenario, **kwargs):
    _, _, path, directory = scenario
    return repair.apply(path, repair.file_hash(path), directory, **kwargs)


def test_apply_null_quotes_preserved_and_roundtrip(scenario):
    db, plan, _, directory = scenario
    assert perform(scenario)['rows'] == 2
    with repair.readonly(db) as c:
        assert c.execute("SELECT 開盤價,最高價,最低價,收盤價 FROM daily_prices WHERE 證券代號='5001'").fetchone() == (None,None,None,20)
        assert c.execute("SELECT extra FROM daily_prices WHERE 日期='20141226'").fetchone() == ('keep',)
    with pytest.raises(ValueError, match='historical PIT'):
        assert_session_revision_safe(db, date(2014,12,27))
    assert_session_revision_safe(db, date(2014,12,26))
    validate_session_replacement(db, plan['rows'], replace_dates=True)
    with pytest.raises(ValueError, match='缺少'):
        validate_session_replacement(db, plan['rows'][:1], replace_dates=True)
    with pytest.raises(ValueError, match='缺少'):
        validate_session_replacement(db, [], replace_all=True)
    validate_session_replacement(db, [{'日期':'20260101','證券代號':'1256','收盤價':1}])
    stale = [dict(r) for r in plan['rows']]
    stale[0]['收盤價'] = '1'
    with pytest.raises(ValueError, match='覆蓋'):
        validate_session_replacement(db, stale)
    assert perform(scenario, rollback=True)['state'] == 'rolled_back'
    assert_session_revision_safe(db, date(2015,1,1))
    with repair.readonly(db) as c:
        assert c.execute('SELECT count(*) FROM daily_prices').fetchone()[0] == 1


@pytest.mark.parametrize('kind', ['source', 'missing_venue', 'existing_date'])
def test_bad_source_or_existing_date_never_changes_db(scenario, kind):
    db, plan, _, directory = scenario
    if kind == 'source':
        Path(plan['sources'][0]['path']).write_text('{}', encoding='utf-8')
    elif kind == 'missing_venue':
        plan['sources'].pop()
    else:
        with sqlite3.connect(db) as c:
            c.execute("INSERT INTO daily_prices (日期,證券代號) VALUES ('20141227','1111')")
    with pytest.raises(ValueError):
        repair.build_plan(db, plan['sources'])
    assert not directory.exists()


@pytest.mark.parametrize('point', ['before_commit', 'after_commit'])
def test_interruption_resume(scenario, monkeypatch, point):
    db, plan, _, directory = scenario
    actual = repair.atomic
    def interrupted(path, body):
        actual(path, body)
        if path.name == ('after_state.json' if point == 'before_commit' else 'receipt.json'):
            raise RuntimeError('simulated interruption')
    monkeypatch.setattr(repair, 'atomic', interrupted)
    with pytest.raises(RuntimeError):
        perform(scenario)
    monkeypatch.setattr(repair, 'atomic', actual)
    assert perform(scenario, resume=True)['state'] == ('rolled_back' if point == 'before_commit' else 'applied')


@pytest.mark.parametrize('drift', ['other_column', 'new_technical', 'backup'])
def test_rollback_refuses_later_changes(scenario, drift):
    db, _, _, directory = scenario
    perform(scenario)
    if drift == 'backup':
        (directory / 'sqlite_before.db').write_bytes(b'tamper')
    else:
        with sqlite3.connect(db) as c:
            if drift == 'other_column':
                c.execute("UPDATE daily_prices SET extra='new' WHERE 日期='20141227'")
            else:
                c.execute("INSERT INTO technical_indicators VALUES ('20141227','1256',50)")
    with pytest.raises(ValueError):
        perform(scenario, rollback=True)
    with repair.readonly(db) as c:
        assert c.execute('SELECT count(*) FROM daily_prices').fetchone()[0] == 3


def test_rollback_cannot_delete_legitimate_later_reimport(scenario):
    db, plan, _, _ = scenario
    perform(scenario)
    perform(scenario, rollback=True)
    with sqlite3.connect(db) as c:
        c.executemany('INSERT INTO daily_prices (' + ','.join(repair.quote(k) for k in repair.FIELDS) + ') VALUES (' + ','.join('?' for _ in repair.FIELDS) + ')', [[r[k] for k in repair.FIELDS] for r in plan['rows']])
    with pytest.raises(ValueError, match='再次刪除'):
        perform(scenario, rollback=True)
    with repair.readonly(db) as c:
        assert c.execute('SELECT count(*) FROM daily_prices').fetchone()[0] == 3


def test_existing_etf_scope_and_invalid_numeric_source(scenario):
    _, plan, _, _ = scenario
    body = json.loads(Path(plan['sources'][0]['path']).read_text(encoding='utf-8'))
    body['tables'][0]['data'][0][0] = '0050'
    assert repair.parse_source(body, venue='twse', day='20141227')[0]['證券代號'] == '0050'
    body['tables'][0]['data'][0][5] = 'not-a-price'
    with pytest.raises(ValueError, match='數值'):
        repair.parse_source(body, venue='twse', day='20141227')


def test_official_odd_lot_activity_does_not_fabricate_ohlc(scenario):
    _,plan,_,_=scenario
    body=json.loads(Path(plan['sources'][0]['path']).read_text(encoding='utf-8'))
    values=body['tables'][0]['data'][0]
    values[2:9]=['25','1','987','--','--','--','--']
    row=repair.parse_source(body,venue='twse',day='20141227')[0]
    assert row['成交股數']==25
    assert all(row[k] is None for k in ('開盤價','最高價','最低價','收盤價'))
