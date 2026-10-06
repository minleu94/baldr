"""指定股票透過既有 universe seam 執行，範圍封存在 request hash。"""
import json
import pytest
from ui_qt.views.recommendation import execution_coordinator as coordinator
from tests.test_r016_saved_result_query_consumers import _execution


def test_explicit_scope_is_sealed_and_forwarded_without_polluting_strategy(monkeypatch):
    captured={}
    def execute(service,config,**kwargs):
        captured.update(kwargs);assert 'manual_research_universe' not in config
        return _execution()
    monkeypatch.setattr(coordinator,'execute_recommendation',execute)
    request=coordinator.RecommendationExecutionRequest({'patterns':{'selected':['triangle']},'signals':{'technical_indicators':['trend']}},universe=('1477',))
    assert json.loads(request.config_snapshot.raw_config_json)['manual_research_universe']==['1477']
    request.execute(object())
    assert captured['universe']==['1477']

@pytest.mark.parametrize('scope',[(),('1477','bad'),('147',),tuple('1477' for _ in range(201))])
def test_invalid_scope_is_blocked_before_execution(scope):
    with pytest.raises(ValueError):coordinator.RecommendationExecutionRequest({},universe=scope)
