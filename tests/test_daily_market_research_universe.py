from dataclasses import replace
import json
import pytest
from app_module.daily_market_research_universe import (load_research_universe_spec, validate_research_universe_manifest_binding, ResearchUniverseContractError)

def config():
    return {"schema_version":"daily-market-research-universe.v1", "universe_id":"bounded", "version":"v1", "as_of_date":"2026-10-05", "method":"daily-market-close-ma.v1", "scope":"bounded_research_cohort", "included_stock_codes":["2382","1477","2330"], "excluded_stock_codes":[{"stock_code":"2317","reason":"明示研究批次排除"}], "population_count":4, "research_only":True, "complete_fixed_cohort":True}

def save(tmp_path, value):
    path=tmp_path/"universe.json";path.write_text(json.dumps(value,ensure_ascii=False),encoding="utf-8");return path

def test_identity_binding_and_member_normalization(tmp_path):
    spec=load_research_universe_spec(save(tmp_path,config()))
    assert spec.included_stock_codes == ("1477","2330","2382")
    assert len(spec.to_manifest_binding()) == 12
    validate_research_universe_manifest_binding(spec,spec.to_manifest_binding())
    assert spec.original_rank_status == {"status":"unknown","reason":"original_rank_immutable_source_missing"}
    assert len(spec.to_dict()["identity_sha256"])==64

@pytest.mark.parametrize("key,value", [("included_stock_codes",["2382","2382"]),("excluded_stock_codes",[{"stock_code":"2382","reason":"overlap"}]),("population_count",True),("population_count",3),("method","legacy-stock-screener"),("as_of_date","20261005"),("research_only",False),("original_rank",1),("rank_status","verified"),("ranking_date","2026-10-04"),("ranking_method","incompatible"),("result_hash","a"*64)])
def test_bad_membership_or_unverified_ranking_input_rejected(tmp_path,key,value):
    value_config=config();value_config[key]=value
    with pytest.raises(ResearchUniverseContractError):load_research_universe_spec(save(tmp_path,value_config))

def test_unknown_denominator_is_explicit(tmp_path):
    value=config();value.update(population_count=None,complete_fixed_cohort=False)
    spec=load_research_universe_spec(save(tmp_path,value))
    assert spec.population_count is None
    value["complete_fixed_cohort"]=True
    with pytest.raises(ResearchUniverseContractError):load_research_universe_spec(save(tmp_path,value))

def test_revision_deletion_and_forged_object_fail_closed(tmp_path):
    path=save(tmp_path,config());spec=load_research_universe_spec(path)
    with pytest.raises(ResearchUniverseContractError): replace(spec,included_stock_codes=("1101",)).assert_source_stable()
    path.write_text(path.read_text(encoding="utf-8")+" ",encoding="utf-8")
    with pytest.raises(ResearchUniverseContractError,match="已變更"):spec.assert_source_stable()
    path.unlink()
    with pytest.raises(ResearchUniverseContractError) as exc:spec.assert_source_stable()
    assert exc.value.code=="universe_source_missing"

def test_binding_date_member_and_method_mismatch(tmp_path):
    spec=load_research_universe_spec(save(tmp_path,config()))
    for key,value in [("as_of_date","2026-10-04"),("method","other"),("included_stock_codes",["1101"]),("source_sha256","b"*64),("research_only",1),("population_count",4.0)]:
        binding=spec.to_manifest_binding();binding[key]=value
        with pytest.raises(ResearchUniverseContractError):validate_research_universe_manifest_binding(spec,binding)

def test_json_duplicates_and_bound_rejected(tmp_path):
    path=tmp_path/"universe.json";path.write_text('{"version":"v1","version":"v2"}')
    with pytest.raises(ResearchUniverseContractError):load_research_universe_spec(path)
    path.write_bytes(b" "*(32*1024+1))
    with pytest.raises(ResearchUniverseContractError):load_research_universe_spec(path)
