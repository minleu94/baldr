"""市場 cutoff 與台北決策日期分開；真正 producer artifact 保存／載入回歸。"""
from dataclasses import replace
from datetime import date,datetime,timezone
import hashlib,json
import pytest
from app_module.saved_recommendation_queries import canonical_scheduled_decision_date,execution_result_config
from app_module.recommendation.contracts import RecommendationResultConfigSnapshot
from app_module.recommendation.persistence import RecommendationExecutionPersistence
from app_module.recommendation.queries import RecommendationExecutionQueries,RecommendationExecutionReadModel
from data_module.result_artifact_store import ResultArtifactStore
from scripts.scheduled import run_scheduled_recommendation_snapshot as producer
from tests.test_scheduled_recommendation_snapshot_wrapper import _fake_recommendation_body_result,_capture_composition

@pytest.fixture
def base_execution(tmp_path, monkeypatch):
    monkeypatch.setenv('PROFILE','test')
    monkeypatch.setenv('DATA_ROOT',str(tmp_path/'data'))
    monkeypatch.setenv('OUTPUT_ROOT',str(tmp_path/'output'))
    monkeypatch.setattr(producer.RecommendationService,'_run_recommendation_body_result',_fake_recommendation_body_result)
    monkeypatch.setattr(producer,'scheduled_now',lambda:datetime(2026,9,22,9,6,tzinfo=timezone.utc))
    captured=_capture_composition(monkeypatch,order=[])
    assert producer.main(['--data-root',str(tmp_path/'data'),'--output-root',str(tmp_path/'output'),'--max-stocks','25','--top-n','5'])==0
    return captured['read_model'].execution


def execution(base, *, decision_at='2026-10-03T12:10:00+00:00', changes=None):
    config=dict(execution_result_config(base))
    config.update({'scheduled_snapshot':True,'decision_date':'2026-10-03','data_as_of_date':'2026-10-02','temporal_mode':'natural_producer_clock','cutoff_policy':'source_latest_available_exact','cutoff_selection':'producer_selected_latest_available_cutoff','date_semantics_schema':'scheduled-recommendation-date-roles.v1','market_cutoff_date':'2026-10-02','decision_timezone':'Asia/Taipei'})
    config.update(changes or {})
    raw=json.dumps(config,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    snapshot=RecommendationResultConfigSnapshot(raw_result_config_json=raw,config_sha256='sha256:'+hashlib.sha256(raw.encode()).hexdigest())
    return replace(base,request=replace(base.request,as_of_date=date(2026,10,2)),context=replace(base.context,as_of_date=date(2026,10,2),decision_at=datetime.fromisoformat(decision_at),result_config_snapshot=snapshot))


def model(value):
    return RecommendationExecutionReadModel(execution=value,label='date contract',notes='',persisted_at=datetime(2026,10,3,13,tzinfo=timezone.utc),payload_hash=None,artifact_location='synthetic')

@pytest.mark.parametrize('clock',['2026-10-03T12:10:00+00:00','2026-10-02T16:30:00+00:00','2026-10-02T09:30:00-07:00'])
def test_weekend_and_cross_timezone_market_day_is_not_decision_day(base_execution, clock):
    assert canonical_scheduled_decision_date(model(execution(base_execution,decision_at=clock)))=='2026-10-03'

@pytest.mark.parametrize('changes',[{'data_as_of_date':'2026-10-04'},{'market_cutoff_date':'2026-10-03'},{'decision_timezone':'America/Los_Angeles'},{'cutoff_policy':'invented'},{'decision_date':'2026-10-02'}])
def test_conflicting_roles_or_future_cutoff_remain_blocked(base_execution, changes):
    try:
        value=execution(base_execution,changes=changes)
    except ValueError:
        return  # typed construction already rejects a conflicting cutoff
    assert canonical_scheduled_decision_date(model(value)) is None


def test_sealed_request_and_context_cutoff_must_agree(base_execution):
    value=execution(base_execution);value=replace(value,request=replace(value.request,as_of_date=date(2026,10,3)))
    assert canonical_scheduled_decision_date(model(value)) is None


def test_actual_artifact_roundtrip_preserves_both_dates_and_hash(tmp_path, base_execution):
    store=ResultArtifactStore(artifact_root=tmp_path/'roundtrip/runs/execution_artifacts',database_path=tmp_path/'roundtrip/runs/recommendation_runs.db')
    persistence=RecommendationExecutionPersistence(store)
    value=execution(base_execution)
    receipt=persistence.save(value,label='date roles',now=lambda:datetime(2026,10,3,13,tzinfo=timezone.utc))
    loaded=RecommendationExecutionQueries(persistence).get(value.result_id)
    assert loaded and loaded.payload_hash==receipt.payload_hash
    assert loaded.execution.request.as_of_date==loaded.execution.context.as_of_date==date(2026,10,2)
    assert canonical_scheduled_decision_date(loaded)=='2026-10-03'


def test_actual_producer_seals_taipei_day_across_pacific_date(tmp_path, monkeypatch, base_execution):
    from tests import test_scheduled_recommendation_snapshot_wrapper as fixture
    monkeypatch.setattr(fixture, '_DECISION_AT', datetime(2026,10,2,23,23,tzinfo=timezone.utc))
    monkeypatch.setattr(producer,'scheduled_now',lambda:datetime(2026,10,2,23,22,tzinfo=timezone.utc))
    captured=_capture_composition(monkeypatch,order=[])
    assert producer.main(['--data-root',str(tmp_path/'rollover-data'),'--output-root',str(tmp_path/'rollover-output'),'--max-stocks','25','--top-n','5'])==0
    value=captured['read_model'].execution
    config=execution_result_config(value)
    assert config['decision_date']=='2026-10-03'
    assert config['market_cutoff_date']==value.context.as_of_date.isoformat()
    assert config['decision_timezone']=='Asia/Taipei'
