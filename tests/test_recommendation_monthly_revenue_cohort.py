"""Synthetic two-market snapshots through actual preparation/update/provider/session."""
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import sqlite3
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from app_module.monthly_revenue_daily_snapshot_update import publish_daily_monthly_revenue_snapshot
from app_module.recommendation.input_preparation import build_default_recommendation_input_preparer
from data_module.current_fundamental_snapshots import monthly_snapshot_rows, insert_observations
from data_module.daily_monthly_revenue_cohort import DailyMonthlyRevenueCohortReader, build_daily_monthly_revenue_cohort_pin
from data_module.daily_source_snapshot import DailySourceSnapshotFileReader, DailySourceTransportCapture, DailySourceUseAcceptance, DailySourceUseScope
from data_module.monthly_revenue_daily_snapshot_preparation import prepare_daily_monthly_revenue_capture
from data_module.monthly_revenue_snapshot_harvester import write_mops_snapshot_csv
from data_module.recommendation_current_fundamental_provider import RecommendationCurrentFundamentalProvider

TAIPEI = ZoneInfo('Asia/Taipei')
PERIOD = '2026-09'


def _fixture(root: Path):
    readers = {}
    batches = {}
    rows = []
    source_root = root/'source'
    source = source_root/'monthly_revenue_mops_snapshots'
    (source/'raw_html').mkdir(parents=True)
    for market, stock, hour, amount in (('twse','2330',10,'1000'),('tpex','6488',12,'2000')):
        market_title = '上市' if market == 'twse' else '上櫃'
        headers = ('公司代號','公司名稱','當月營收','上月營收','去年當月營收','當月累計營收','去年累計營收')
        cells = (stock, '合成測試', amount, '900', '800', '9000', '8000')
        html = f'<html><body>{market_title}公司115年9月份 單位：新臺幣千元<table>'
        html += '<tr>'+''.join(f'<th>{value}</th>' for value in headers)+'</tr>'
        html += '<tr>'+''.join(f'<td>{value}</td>' for value in cells)+'</tr></table></body></html>'
        raw = html.encode('big5')
        scope = DailySourceUseScope('fundamental_current_observations.monthly_revenue','mops.monthly_revenue_static_snapshot',market,'mops-current-revenue-normalizer.v2','mops-static-snapshot.v2','TWD','recommendation_current_fundamental')
        url = f'https://mopsov.twse.com.tw/nas/t21/{"sii" if market == "twse" else "otc"}/t21sc03_115_9_0.html'
        acceptance = DailySourceUseAcceptance(scope=scope,acceptance_id=f'synthetic-{market}-accepted',accepted_at=datetime(2026,10,2,8,tzinfo=TAIPEI),official_source_endpoint=url,document_chain=(url,'synthetic-only'),acceptance_evidence_ref='synthetic-cohort-test',authorization_scope='recommendation_current_fundamental synthetic_only')
        capture = DailySourceTransportCapture(raw,url,200,'text/html; charset=big5','big5','http_content_type_charset',datetime(2026,10,2,hour,5,tzinfo=TAIPEI),sha256(raw).hexdigest(),True,len(raw),str(len(raw)),f'eof:synthetic-{market}-fixture')
        clocks = iter(datetime(2026,10,2,hour,minute,tzinfo=TAIPEI) for minute in (8,10,20,25,30))
        batch_id = f'synthetic-{market}-202609'
        result = publish_daily_monthly_revenue_snapshot(root=root/f'{market}-snapshots',capture=capture,period=PERIOD,batch_id=batch_id,source_batch_started_at=datetime(2026,10,2,hour,0,tzinfo=TAIPEI),use_acceptance=acceptance,scope=scope,clock=lambda:next(clocks),check_cancel=lambda:False)
        assert result.success, result
        prepared = prepare_daily_monthly_revenue_capture(capture=capture,scope=scope,period=PERIOD,validation_id=f'synthetic-{market}-parse')
        (source/'raw_html'/f'{market}_{PERIOD}.html').write_bytes(b'\xef\xbb\xbf'+prepared.canonical_source_bytes)
        csv = source/f'mops_monthly_revenue_snapshot_{market}_fixture.csv'
        write_mops_snapshot_csv(csv, prepared.rows)
        observations = monthly_snapshot_rows(csv, verified_source_versions={prepared.source_version})
        for observation in observations:
            observation['observed_at'] = datetime(2026,10,2,hour,8,tzinfo=TAIPEI).isoformat()
        rows.extend(observations)
        readers[market] = DailySourceSnapshotFileReader(root/f'{market}-snapshots',trusted_acceptance=acceptance)
        batches[market] = batch_id
    database = root/'current.sqlite'
    with sqlite3.connect(database) as connection:
        assert insert_observations(connection, rows) == 4
        connection.commit()
    pin = build_daily_monthly_revenue_cohort_pin(period=PERIOD,required_markets=('twse','tpex'),batch_ids=batches,readers=readers)
    reader = DailyMonthlyRevenueCohortReader(pin=pin,market_readers=readers,expected_cohort_sha256=pin.cohort_sha256)
    provider = RecommendationCurrentFundamentalProvider(db_file=database,output_root=source_root,monthly_source_root=source_root,daily_source_snapshot_reader=reader)
    return provider, pin, reader, readers, SimpleNamespace(db_file=database,output_root=source_root), batches


def test_two_markets_use_only_complete_cohort_and_same_later_hour(tmp_path):
    provider,pin,reader,_,config,batches = _fixture(tmp_path)
    before = sha256(config.db_file.read_bytes()).hexdigest()
    gate = datetime(2026,10,2,13,tzinfo=TAIPEI)
    assert pin.available_hour == gate
    for stock,market,amount in (('2330','twse','1000000'),('6488','tpex','2000000')):
        early = provider.load_monthly_revenues(stock_code=stock,cutoff_at=gate-timedelta(microseconds=1),pinned_daily_cohort=pin)
        assert not early.observations and 'daily_source_cohort_not_available_at_cutoff' in early.diagnostics
        current = provider.load_monthly_revenues(stock_code=stock,cutoff_at=gate,pinned_daily_cohort=pin)
        assert current.status == 'ready' and len(current.observations) == 1, current
        row = current.observations[0]
        assert row.revenue == Decimal(amount) and row.available_at == gate
        assert row.availability_snapshot_batch_id == batches[market]
        assert not row.formal_pit_eligible and current.comparison_baseline.available_at == gate
    assert sha256(config.db_file.read_bytes()).hexdigest() == before


def test_other_required_market_damage_blocks_even_intact_stock(tmp_path):
    provider,pin,_,readers,config,batches = _fixture(tmp_path)
    target = readers['tpex'].root/batches['tpex']/'manifest.json'
    target.write_bytes(target.read_bytes()+b' ')
    before = sha256(config.db_file.read_bytes()).hexdigest()
    result = provider.load_monthly_revenues(stock_code='2330',cutoff_at=pin.available_hour,pinned_daily_cohort=pin)
    assert result.status == 'unavailable' and not result.observations
    assert any('daily_source_cohort_rejected:' in item for item in result.diagnostics)
    assert sha256(config.db_file.read_bytes()).hexdigest() == before


def test_scalar_pin_cannot_bypass_required_group_or_mix_with_cohort(tmp_path):
    provider,pin,_,_,_,batches = _fixture(tmp_path)
    scalar = provider.load_monthly_revenues(stock_code='2330',cutoff_at=pin.available_hour,pinned_daily_batch_id=batches['twse'])
    mixed = provider.load_monthly_revenues(stock_code='2330',cutoff_at=pin.available_hour,pinned_daily_batch_id=batches['twse'],pinned_daily_cohort=pin)
    assert scalar.status == mixed.status == 'unavailable'
    assert not scalar.observations and not mixed.observations


def test_default_normal_session_freezes_reader_pin_clock_and_records_same_context(tmp_path):
    _,pin,reader,_,config,batches = _fixture(tmp_path)
    preparer = build_default_recommendation_input_preparer(config,market_data_provider=lambda:pd.DataFrame(),market_session_cadence_factory=lambda *_args,**_kwargs:None,daily_monthly_cohort_reader=reader)
    session = preparer.begin(config,invocation_frozen_at=pin.available_hour)
    session.resolve_cutoff(runtime_config={},as_of_date=None,historical_research=False,select_latest_available_cutoff=False)
    assert not session.daily_monthly_cohort_source_context()
    for stock in ('2330','6488'):
        result = session.load_current_monthly_revenues(stock_code=stock,cutoff_at=pin.available_hour)
        assert result.status == 'ready', result
    context = session.daily_monthly_cohort_source_context()
    assert context['cohort_sha256'] == pin.cohort_sha256 and context['pin'] == pin.to_dict()
    assert context['read_outcome_by_stock'] == {'2330':'ready','6488':'ready'}
    assert context['historical_pit_eligible'] is context['formal_pit_eligible'] is False
    context['read_outcome_by_stock']['2330'] = 'changed'
    assert session.daily_monthly_cohort_source_context()['read_outcome_by_stock']['2330'] == 'ready'
    later = session.load_current_monthly_revenues(stock_code='2330',cutoff_at=pin.available_hour+timedelta(hours=1))
    assert later.status == 'unavailable' and not later.observations


@pytest.mark.parametrize('mode',['historical','select_latest'])
def test_pinned_session_never_relabels_non_natural_as_daily(tmp_path,mode):
    _,pin,reader,_,config,_ = _fixture(tmp_path)
    preparer = build_default_recommendation_input_preparer(config,market_data_provider=lambda:pd.DataFrame(),market_session_cadence_factory=lambda *_args,**_kwargs:None,daily_monthly_cohort_reader=reader)
    session = preparer.begin(config,invocation_frozen_at=pin.available_hour)
    session.resolve_cutoff(runtime_config={},as_of_date='2026-10-01' if mode=='historical' else None,historical_research=mode=='historical',select_latest_available_cutoff=mode=='select_latest')
    result = session.load_current_monthly_revenues(stock_code='2330',cutoff_at=pin.available_hour)
    assert result.status == 'unavailable' and not result.observations
    assert not session.daily_monthly_cohort_source_context()
