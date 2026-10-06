"""週六交易證據須確認官方日期與個股價格表，不以任意非空回應認定。"""
from data_module.market_data_integrity import official_twse_price_table


def test_current_and_legacy_price_table_acceptance():
    table = {'fields': ['證券代號', '證券名稱', '收盤價'], 'data': [['1256', '鮮活', '100']]}
    modern = {'stat': 'OK', 'date': '20141227', 'tables': [table]}
    assert official_twse_price_table(modern, '20141227') == table
    assert official_twse_price_table({'stat': 'OK', 'date': '20141227', **table}, '20141227') is not None


def test_wrong_day_empty_or_index_only_cannot_certify_session():
    for body in [
        {'stat': 'OK', 'date': '20141226', 'tables': [{'fields': ['證券代號', '證券名稱', '收盤價'], 'data': [['1256', '鮮活', '100']]}]},
        {'stat': 'OK', 'date': '20141227', 'data': [['arbitrary']]},
        {'stat': 'OK', 'date': '20141227', 'tables': [{'fields': ['指數', '收盤指數'], 'data': [['TAIEX', '100']]}]},
        {'stat': 'OK', 'date': '20141227', 'tables': []},
    ]:
        assert official_twse_price_table(body, '20141227') is None
