from decimal import Decimal
import hashlib
import inspect
import pickle
from pathlib import Path
import subprocess
import sys
from typing import get_args, get_origin

import joblib
import pytest
from app_module.dtos import RecommendationDTO, RecommendationResultDTO

def test_recommendation_dto_roundtrip():
    dto = RecommendationDTO(
        stock_code="1101",
        stock_name="台泥",
        close_price=45.5,
        price_change=1.2,
        total_score=85.5,
        indicator_score=80.0,
        pattern_score=90.0,
        volume_score=85.0,
        recommendation_reasons="均線多頭排列",
        industry="水泥工業",
        regime_match=True,
        score_percentile_bp=8000,
        eligible_universe_size=50,
        eligible_universe_date="2026-06-12",
        ranking_method="nearest_rank",
        threshold_mode="quantile"
    )
    
    serialized = dto.to_dict()
    assert serialized["score_percentile_bp"] == 8000
    assert serialized["eligible_universe_size"] == 50
    assert serialized["eligible_universe_date"] == "2026-06-12"
    assert serialized["ranking_method"] == "nearest_rank"
    assert serialized["threshold_mode"] == "quantile"
    
    # 檢查中文 key
    assert serialized["百分位"] == "80.00%"
    assert serialized["母體數"] == 50
    assert serialized["門檻模式"] == "百分位"
    
    deserialized = RecommendationDTO.from_dict(serialized)
    assert deserialized.stock_code == "1101"
    assert deserialized.stock_name == "台泥"
    assert deserialized.close_price == 45.5
    assert deserialized.price_change == 1.2
    assert deserialized.total_score == 85.5
    assert deserialized.score_percentile_bp == 8000
    assert deserialized.threshold_mode == "quantile"

def test_recommendation_dto_compat_with_legacy_and_chinese_keys():
    # 只有中文 key，且缺少任何 metadata 欄位（歷史 JSON 格式）
    legacy_data = {
        "證券代號": "2330",
        "證券名稱": "台積電",
        "收盤價": 600.0,
        "漲幅%": 2.5,
        "總分": 90.0,
        "指標分": 85.0,
        "圖形分": 95.0,
        "成交量分": 90.0,
        "推薦理由": "W底形成",
        "產業": "半導體業",
        "Regime匹配": "是"
    }
    
    deserialized = RecommendationDTO.from_dict(legacy_data)
    assert deserialized.stock_code == "2330"
    assert deserialized.stock_name == "台積電"
    assert deserialized.close_price == 600.0
    assert deserialized.price_change == 2.5
    assert deserialized.total_score == 90.0
    assert deserialized.regime_match is True
    # 預設值
    assert deserialized.score_percentile_bp is None
    assert deserialized.threshold_mode == "fixed"

def test_recommendation_result_dto_roundtrip():
    result_dto = RecommendationResultDTO(
        result_id="rec_20260613_120000",
        result_name="推薦結果_測試",
        config={"param1": "val1"},
        recommendations=[
            RecommendationDTO(
                stock_code="1101",
                stock_name="台泥",
                close_price=45.5,
                price_change=1.2,
                total_score=85.5,
                indicator_score=80.0,
                pattern_score=90.0,
                volume_score=85.0,
                recommendation_reasons="均線多頭",
                industry="水泥",
                regime_match=True,
                score_percentile_bp=8000,
                threshold_mode="quantile"
            )
        ],
        regime="Trend",
        created_at="2026-06-13T12:00:00",
        notes="測試記錄"
    )
    
    serialized = result_dto.to_dict()
    deserialized = RecommendationResultDTO.from_dict(serialized)
    
    assert deserialized.result_id == "rec_20260613_120000"
    assert len(deserialized.recommendations) == 1
    assert deserialized.recommendations[0].stock_code == "1101"
    assert deserialized.recommendations[0].score_percentile_bp == 8000
    assert deserialized.recommendations[0].threshold_mode == "quantile"


def test_recommendation_dto_owner_preserves_legacy_nominal_and_reflection_abi():
    from app_module.recommendation.legacy_dtos import (
        RecommendationDTO as CanonicalRecommendationDTO,
        RecommendationResultDTO as CanonicalRecommendationResultDTO,
    )

    assert CanonicalRecommendationDTO is RecommendationDTO
    assert CanonicalRecommendationResultDTO is RecommendationResultDTO

    for dto_type in (RecommendationDTO, RecommendationResultDTO):
        assert dto_type.__module__ == "app_module.dtos"
        assert dto_type.__qualname__ == dto_type.__name__
        for method_name in ("__init__", "__repr__", "__eq__", "to_dict"):
            method = getattr(dto_type, method_name)
            assert method.__module__ == "app_module.dtos"
            assert method.__qualname__ == f"{dto_type.__name__}.{method_name}"
        from_dict = dto_type.from_dict.__func__
        assert from_dict.__module__ == "app_module.dtos"
        assert from_dict.__qualname__ == f"{dto_type.__name__}.from_dict"

        repr_inner = getattr(dto_type.__repr__, "__wrapped__", None)
        assert repr_inner is not None
        assert repr_inner.__module__ == "app_module.dtos"
        assert repr_inner.__qualname__ == "__create_fn__.<locals>.__repr__"

    post_init = RecommendationResultDTO.__post_init__
    assert post_init.__module__ == "app_module.dtos"
    assert post_init.__qualname__ == "RecommendationResultDTO.__post_init__"

    assert str(inspect.signature(RecommendationDTO.__init__)) == (
        "(self, stock_code: str, stock_name: str, close_price: float | decimal.Decimal, "
        "price_change: float, total_score: float, indicator_score: float, "
        "pattern_score: float, volume_score: float, recommendation_reasons: str, "
        "industry: str, regime_match: bool, score_percentile_bp: Optional[int] = None, "
        "eligible_universe_size: Optional[int] = None, "
        "eligible_universe_date: Optional[str] = None, ranking_method: Optional[str] = None, "
        "threshold_mode: str = 'fixed', ranking_score_bp: Optional[int] = None, "
        "calibrated_probability_bp: Optional[int] = None, "
        "calibrated_probability_status: str = 'unavailable', "
        "after_cost_profit_probability_bp: Optional[int] = None, "
        "after_cost_profit_probability_status: str = 'unavailable', "
        "evidence_confidence: str = '', sample_size: Optional[int] = None, "
        "cost_basis_bp: Optional[int] = None, calibration_model_version: str = '', "
        "calibration_dataset_version: str = '', calibration_horizon: str = '', "
        "calibration_status: str = 'unavailable', calibration_source: str = '', "
        "calibration_warnings: List[str] = <factory>, "
        "calibration_source_trace: List[str] = <factory>, "
        "calibration_probability_transform_id: str = '', "
        "calibration_probability_baseline_id: str = '', "
        "calibration_probability_baseline_kind: str = '', "
        "calibration_probability_baseline_probability_bp: Optional[int] = None, "
        "calibration_raw_probability_bp: Optional[int] = None, "
        "calibration_raw_after_cost_probability_bp: Optional[int] = None, "
        "calibration_provenance: Dict[str, Any] = <factory>) -> None"
    )
    assert str(inspect.signature(RecommendationResultDTO.__init__)) == (
        "(self, result_id: str, result_name: str, config: Dict[str, Any], "
        "recommendations: List[app_module.dtos.RecommendationDTO], "
        "regime: Optional[str] = None, created_at: Optional[str] = None, notes: str = '', "
        "excluded_candidates_json: List[Dict[str, Any]] = <factory>, "
        "screening_matrix_json: List[Dict[str, Any]] = <factory>, "
        "why_not_payload_json: List[Dict[str, Any]] = <factory>, "
        "liquidity_gate_payload_json: List[Dict[str, Any]] = <factory>, "
        "exclusion_quality: Optional[str] = None, "
        "exclusion_warnings_json: List[str] = <factory>, "
        "run_context: Dict[str, Any] = <factory>) -> None"
    )
    assert str(inspect.signature(RecommendationDTO.to_dict)) == "(self) -> dict"
    assert str(inspect.signature(RecommendationDTO.from_dict)) == (
        "(data: dict) -> 'RecommendationDTO'"
    )
    assert str(inspect.signature(RecommendationResultDTO.to_dict)) == "(self) -> dict"
    assert str(inspect.signature(RecommendationResultDTO.from_dict)) == (
        "(data: dict) -> 'RecommendationResultDTO'"
    )

    assert RecommendationDTO.__annotations__["close_price"] == float | Decimal
    recommendations_annotation = RecommendationResultDTO.__annotations__["recommendations"]
    assert get_origin(recommendations_annotation) is list
    assert get_args(recommendations_annotation) == (RecommendationDTO,)


def test_recommendation_dto_leaf_type_hints_work_without_loading_old_facade():
    code = r"""
import sys
from typing import get_args, get_origin, get_type_hints
from app_module.recommendation.legacy_dtos import RecommendationDTO, RecommendationResultDTO
assert 'app_module.dtos' not in sys.modules
assert get_type_hints(RecommendationDTO)['close_price'] == float | __import__('decimal').Decimal
recommendations = get_type_hints(RecommendationResultDTO)['recommendations']
assert get_origin(recommendations) is list
assert get_args(recommendations) == (RecommendationDTO,)
assert get_type_hints(RecommendationDTO.from_dict)['return'] is RecommendationDTO
assert get_type_hints(RecommendationResultDTO.from_dict)['return'] is RecommendationResultDTO
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_recommendation_dto_legacy_pickle_and_joblib_bytes_load_in_fresh_process(
    tmp_path: Path,
):
    recommendation = RecommendationDTO(
        stock_code="2330",
        stock_name="合成台積電",
        close_price=Decimal("123.4500"),
        price_change=Decimal("1.25"),
        total_score=Decimal("82.500"),
        indicator_score=Decimal("50"),
        pattern_score=Decimal("20"),
        volume_score=Decimal("12.5"),
        recommendation_reasons="合成回歸樣本",
        industry="合成產業",
        regime_match=True,
        score_percentile_bp=8250,
        eligible_universe_size=2,
        eligible_universe_date="2026-09-25",
        ranking_method="synthetic-ranking-v1",
        threshold_mode="fixed",
        ranking_score_bp=8250,
        calibrated_probability_bp=7100,
        calibrated_probability_status="available",
        after_cost_profit_probability_bp=6800,
        after_cost_profit_probability_status="available",
        evidence_confidence="synthetic",
        sample_size=12,
        cost_basis_bp=35,
        calibration_model_version="synthetic-model-v1",
        calibration_dataset_version="synthetic-data-v1",
        calibration_horizon="5d",
        calibration_status="active_candidate",
        calibration_source="synthetic-source",
        calibration_warnings=["synthetic-warning"],
        calibration_source_trace=["synthetic-trace"],
        calibration_probability_transform_id="synthetic-transform",
        calibration_probability_baseline_id="synthetic-baseline",
        calibration_probability_baseline_kind="synthetic-kind",
        calibration_probability_baseline_probability_bp=5000,
        calibration_raw_probability_bp=7200,
        calibration_raw_after_cost_probability_bp=6900,
        calibration_provenance={"source": "synthetic controlled fixture"},
    )
    result = RecommendationResultDTO(
        result_id="rec05-synthetic-abi",
        result_name="synthetic ABI baseline",
        config={"profile_id": "synthetic-profile", "max_stocks": 2},
        recommendations=[recommendation],
        regime="Trend",
        created_at="2026-09-25T12:00:00+00:00",
        notes="synthetic-only; no production artifacts",
        excluded_candidates_json=[{"stock_code": "2317", "reason": "synthetic"}],
        screening_matrix_json=[{"stock_code": "2330", "status": "pass"}],
        why_not_payload_json=[],
        liquidity_gate_payload_json=[],
        exclusion_quality="observed",
        exclusion_warnings_json=["synthetic-warning"],
        run_context={"as_of_date": "2026-09-25", "data_as_of_date": "2026-09-25"},
    )
    expected_hashes = {
        4: "d9bba2e3a6881f7a381b1ed9c6972e0241200608302ced3a252f0b159dc53d31",
        5: "42bc17eed498441ccfc33b284722fb7de4697054fe2cf1e70c0d5c3e793d56d7",
    }
    paths = []
    for protocol, expected_hash in expected_hashes.items():
        path = tmp_path / f"recommendation_result_protocol_{protocol}.pkl"
        raw = pickle.dumps(result, protocol=protocol)
        assert hashlib.sha256(raw).hexdigest() == expected_hash
        path.write_bytes(raw)
        paths.append(str(path))

    joblib_path = tmp_path / "recommendation_result.joblib"
    joblib.dump(result, joblib_path, compress=0, protocol=4)
    assert hashlib.sha256(joblib_path.read_bytes()).hexdigest() == expected_hashes[4]
    paths.append(str(joblib_path))

    code = r"""
from pathlib import Path
import pickle
import sys
import joblib
from app_module.recommendation.legacy_dtos import RecommendationDTO, RecommendationResultDTO
from app_module.dtos import RecommendationDTO as OldRecommendationDTO
from app_module.dtos import RecommendationResultDTO as OldRecommendationResultDTO
assert RecommendationDTO is OldRecommendationDTO
assert RecommendationResultDTO is OldRecommendationResultDTO
for path in sys.argv[1:]:
    value = joblib.load(path) if path.endswith('.joblib') else pickle.loads(Path(path).read_bytes())
    assert type(value) is RecommendationResultDTO
    assert type(value.recommendations[0]) is RecommendationDTO
    assert value.result_id == 'rec05-synthetic-abi'
    assert value.recommendations[0].stock_code == '2330'
    assert value.recommendations[0].calibration_provenance == {'source': 'synthetic controlled fixture'}
"""
    completed = subprocess.run(
        [sys.executable, "-c", code, *paths],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
