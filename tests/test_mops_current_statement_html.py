"""MOPS財報明示單位與基礎的安全現況正規化。"""
from datetime import datetime,timezone
import sqlite3
import pytest
from data_module.mops_current_statement_html import parse_current_statement_html
from data_module.current_fundamental_snapshots import insert_observations


def html(unit='新台幣仟元',basis='累計'):
    return f'<h1>上市公司第二季資料</h1><p>單位：{unit} 本期{basis}金額</p><table><tr><th>公司代號</th><th>公司名稱</th><th>營業收入</th><th>基本每股盈餘（元）</th><th>庫藏股股數（單位：股）</th></tr><tr><td>2330</td><td>台積電</td><td>1,234.5</td><td>5.67</td><td>100</td></tr></table>'


def test_unit_scale_eps_and_shares_keep_their_units():
    rows,summary=parse_current_statement_html(html(),market='twse',period='2026-Q2',statement='income',observed_at=datetime.now(timezone.utc))
    assert [(r['value'],r['unit']) for r in rows]==[('1234500.0','TWD'),('5.67','TWD/share'),('100','shares')]
    assert all('年初累計' in r['item_name'] for r in rows)
    assert all(r['period_basis']=='year_to_date_cumulative' for r in rows)
    assert all(r['basis_verified']=='1' and r['aggregate_feature_eligible']=='0' for r in rows)
    assert all('mops-current-statement-html.v3:' in r['source_version'] for r in rows)
    assert all(r['source_available_at']=='' for r in rows)
    assert all(r['source_version'].endswith('captured_at:unknown') for r in rows)
    assert summary['source_available_at'] is None
    assert summary['historical_pit_eligible'] is False
    assert all(r['source_available_at']=='' for r in rows)
    assert all(r['source_version'].endswith('captured_at:unknown') for r in rows)
    assert summary['source_available_at'] is None


@pytest.mark.parametrize('body,reason',[(html(unit='未知'),'單位'),(html(basis='未知'),'累計'),(html().replace('第二季','第一季'),'季度')])
def test_unverified_unit_basis_or_period_block(body,reason):
    with pytest.raises(ValueError,match=reason):
        parse_current_statement_html(body,market='twse',period='2026-Q2',statement='income',observed_at=datetime.now(timezone.utc))


def test_cashflow_reports_source_period_without_guessing_cumulative_basis():
    rows,summary=parse_current_statement_html(html(basis=''),market='twse',period='2026-Q2',statement='cashflow',observed_at=datetime.now(timezone.utc))
    assert summary['basis_verified'] is False
    assert summary['aggregate_feature_eligible'] is False
    assert '期間基礎未明示' in rows[0]['item_name']
    assert rows[0]['value']=='1234500.0' and rows[0]['unit']=='TWD'
    assert rows[0]['period_basis']=='unknown'
    assert rows[0]['basis_verified']=='0' and rows[0]['aggregate_feature_eligible']=='0'


def test_balance_is_verified_as_period_end():
    rows,summary=parse_current_statement_html(html(),market='twse',period='2026-Q2',statement='balance',observed_at=datetime.now(timezone.utc))
    assert summary['period_basis']=='period_end'
    assert all(r['period_basis']=='period_end' for r in rows)
    assert all(r['basis_verified']=='1' and r['aggregate_feature_eligible']=='0' for r in rows)


def test_source_capture_clock_is_preserved_separately_from_local_observation():
    source_time=datetime(2026,9,30,12,tzinfo=timezone.utc)
    observed_at=datetime(2026,10,1,12,tzinfo=timezone.utc)
    rows,summary=parse_current_statement_html(
        html(),market='twse',period='2026-Q2',statement='income',
        observed_at=observed_at,source_available_at=source_time,
    )
    assert rows[0]['observed_at']==observed_at.isoformat()
    assert rows[0]['source_available_at']==source_time.isoformat()
    assert rows[0]['source_version'].endswith(f'captured_at:{source_time.isoformat()}')
    assert summary['source_available_at']==source_time.isoformat()


def test_verified_statement_basis_does_not_require_or_invent_capture_clock():
    observed = datetime.now(timezone.utc)
    rows, _summary = parse_current_statement_html(
        html(),
        market='twse',
        period='2026-Q2',
        statement='income',
        observed_at=observed,
        source_available_at=None,
    )
    connection = sqlite3.connect(':memory:')
    assert insert_observations(connection, rows) == len(rows)
    stored = connection.execute(
        "SELECT period_basis,basis_verified,aggregate_feature_eligible,source_available_at "
        "FROM fundamental_current_observations ORDER BY item_code LIMIT 1"
    ).fetchone()
    assert stored == ('year_to_date_cumulative', 1, 0, None)
    connection.close()
