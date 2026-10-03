"""MOPS財報明示單位與基礎的安全現況正規化。"""
from datetime import datetime,timezone
import pytest
from data_module.mops_current_statement_html import parse_current_statement_html


def html(unit='新台幣仟元',basis='累計'):
    return f'<h1>上市公司第二季資料</h1><p>單位：{unit} 本期{basis}金額</p><table><tr><th>公司代號</th><th>公司名稱</th><th>營業收入</th><th>基本每股盈餘（元）</th><th>庫藏股股數（單位：股）</th></tr><tr><td>2330</td><td>台積電</td><td>1,234.5</td><td>5.67</td><td>100</td></tr></table>'


def test_unit_scale_eps_and_shares_keep_their_units():
    rows,summary=parse_current_statement_html(html(),market='twse',period='2026-Q2',statement='income',observed_at=datetime.now(timezone.utc))
    assert [(r['value'],r['unit']) for r in rows]==[('1234500.0','TWD'),('5.67','TWD/share'),('100','shares')]
    assert all('年初累計' in r['item_name'] for r in rows)
    assert summary['historical_pit_eligible'] is False


@pytest.mark.parametrize('body,reason',[(html(unit='未知'),'單位'),(html(basis='未知'),'累計'),(html().replace('第二季','第一季'),'季度')])
def test_unverified_unit_basis_or_period_block(body,reason):
    with pytest.raises(ValueError,match=reason):
        parse_current_statement_html(body,market='twse',period='2026-Q2',statement='income',observed_at=datetime.now(timezone.utc))


def test_cashflow_reports_source_period_without_guessing_cumulative_basis():
    rows,summary=parse_current_statement_html(html(basis=''),market='twse',period='2026-Q2',statement='cashflow',observed_at=datetime.now(timezone.utc))
    assert summary['basis_verified'] is False
    assert summary['aggregate_feature_eligible'] is False
    assert '期間基礎未明示' in rows[0]['item_name']
