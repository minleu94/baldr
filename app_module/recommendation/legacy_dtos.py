"""推薦 v1 DTO；只保留 canonical execution 的明示 legacy 投影型別。"""

from copy import deepcopy
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Mapping, Optional, cast


@dataclass
class RecommendationDTO:
    """股票推薦數據傳輸對象"""
    stock_code: str
    stock_name: str
    close_price: float | Decimal
    price_change: float  # 漲幅百分比
    total_score: float
    indicator_score: float
    pattern_score: float
    volume_score: float
    recommendation_reasons: str
    industry: str
    regime_match: bool

    # 追溯元數據
    score_percentile_bp: Optional[int] = None
    eligible_universe_size: Optional[int] = None
    eligible_universe_date: Optional[str] = None
    ranking_method: Optional[str] = None
    threshold_mode: str = "fixed"
    # 受控 recommendation calibration projection；缺值代表 rule-only/unavailable。
    ranking_score_bp: Optional[int] = None
    calibrated_probability_bp: Optional[int] = None
    calibrated_probability_status: str = "unavailable"
    after_cost_profit_probability_bp: Optional[int] = None
    after_cost_profit_probability_status: str = "unavailable"
    evidence_confidence: str = ""
    sample_size: Optional[int] = None
    cost_basis_bp: Optional[int] = None
    calibration_model_version: str = ""
    calibration_dataset_version: str = ""
    calibration_horizon: str = ""
    calibration_status: str = "unavailable"
    calibration_source: str = ""
    calibration_warnings: List[str] = field(default_factory=list)
    calibration_source_trace: List[str] = field(default_factory=list)
    # 保留 consumer 的 effective probability lineage，讓下游 Advice／Portfolio／呈現
    # 可以辨識實際送達值、raw 值與遞迴 cap 的基準；缺值仍代表舊版 rule-only 資料。
    calibration_probability_transform_id: str = ""
    calibration_probability_baseline_id: str = ""
    calibration_probability_baseline_kind: str = ""
    calibration_probability_baseline_probability_bp: Optional[int] = None
    calibration_raw_probability_bp: Optional[int] = None
    calibration_raw_after_cost_probability_bp: Optional[int] = None
    # 結構化 provenance；空值代表舊版 rule-only 或歷史保存資料。
    calibration_provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """匯出明示的 legacy wire shape；新格式由 execution codec 處理。"""
        from app_module.recommendation.codec import encode_legacy_recommendation

        return encode_legacy_recommendation(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'RecommendationDTO':
        """透過明示 legacy decoder 還原中英文歷史欄位。"""
        from app_module.recommendation.codec import decode_legacy_recommendation

        return decode_legacy_recommendation(data, dto_type=cls)


@dataclass
class RecommendationResultDTO:
    """推薦結果數據傳輸對象（固定欄位，可保存、可追溯）"""
    result_id: str  # 結果ID（唯一標識）
    result_name: str  # 結果名稱
    config: Dict[str, Any]  # 策略配置（完整配置）
    recommendations: List[RecommendationDTO]  # 推薦股票列表
    regime: Optional[str] = None  # 市場狀態
    created_at: Optional[str] = None  # 創建時間
    notes: str = ""  # 備註

    excluded_candidates_json: List[Dict[str, Any]] = field(default_factory=list)
    screening_matrix_json: List[Dict[str, Any]] = field(default_factory=list)
    why_not_payload_json: List[Dict[str, Any]] = field(default_factory=list)
    liquidity_gate_payload_json: List[Dict[str, Any]] = field(default_factory=list)
    exclusion_quality: Optional[str] = None
    exclusion_warnings_json: List[str] = field(default_factory=list)
    run_context: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """相容既有保存協調器，以 config 接點接收完整執行快照。"""
        self.config = deepcopy(self.config)
        supplied_context = self.config.pop("_recommendation_run_context", {})
        self.run_context = deepcopy(self.run_context or supplied_context)

    def to_dict(self) -> dict:
        """轉換為字典"""
        return {
            'result_id': self.result_id,
            'result_name': self.result_name,
            'config': self.config,
            'recommendations': [rec.to_dict() for rec in self.recommendations],
            'regime': self.regime,
            'created_at': self.created_at,
            'notes': self.notes,
            'excluded_candidates_json': self.excluded_candidates_json,
            'screening_matrix_json': self.screening_matrix_json,
            'why_not_payload_json': self.why_not_payload_json,
            'liquidity_gate_payload_json': self.liquidity_gate_payload_json,
            'exclusion_quality': self.exclusion_quality,
            'exclusion_warnings_json': self.exclusion_warnings_json,
            'run_context': deepcopy(self.run_context),
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'RecommendationResultDTO':
        """從字典創建對象"""
        recommendations = [
            RecommendationDTO.from_dict(rec) if isinstance(rec, dict) else rec
            for rec in data.get('recommendations', [])
        ]
        return cls(
            result_id=data.get('result_id', ''),
            result_name=data.get('result_name', ''),
            config=data.get('config', {}),
            recommendations=recommendations,
            regime=data.get('regime'),
            created_at=data.get('created_at'),
            notes=data.get('notes', ''),
            excluded_candidates_json=list(data.get('excluded_candidates_json') or []),
            screening_matrix_json=list(data.get('screening_matrix_json') or []),
            why_not_payload_json=list(data.get('why_not_payload_json') or []),
            liquidity_gate_payload_json=list(data.get('liquidity_gate_payload_json') or []),
            exclusion_quality=data.get('exclusion_quality'),
            exclusion_warnings_json=[str(item) for item in (data.get('exclusion_warnings_json') or [])],
            run_context=deepcopy(data.get('run_context') or {}),
        )



# 舊 public/pickle path 保持穩定；實際 class owner 是此 leaf module。
for _legacy_dto in (RecommendationDTO, RecommendationResultDTO):
    setattr(_legacy_dto, "__module__", "app_module.dtos")
    setattr(_legacy_dto.to_dict, "__module__", "app_module.dtos")
    for _method_name in ("__init__", "__repr__", "__eq__", "__post_init__"):
        _legacy_method = getattr(_legacy_dto, _method_name, None)
        if _legacy_method is not None:
            setattr(_legacy_method, "__module__", "app_module.dtos")
    _legacy_repr = _legacy_dto.__repr__
    _legacy_repr_inner = getattr(_legacy_repr, "__wrapped__", None)
    if _legacy_repr_inner is not None:
        setattr(_legacy_repr_inner, "__module__", "app_module.dtos")

setattr(vars(RecommendationDTO)["from_dict"].__func__, "__module__", "app_module.dtos")
setattr(vars(RecommendationResultDTO)["from_dict"].__func__, "__module__", "app_module.dtos")
