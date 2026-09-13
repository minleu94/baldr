"""觀察清單的唯讀已保存個股分析，不重新評分或改寫來源。"""
from contextlib import closing
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import sqlite3

from app_module.dtos import RecommendationResultDTO


@dataclass(frozen=True)
class WatchlistAnalysisDTO:
    stock_code: str
    status: str
    analysis_date: str = ""
    result_id: str = ""
    score: str = ""
    close_price: str = ""
    reasons: str = ""
    message: str = ""
    # 保存來源中的決策／資料日期與 Profile；舊保存結果缺欄位時維持空值。
    decision_date: str = ""
    data_date: str = ""
    profile_id: str = ""
    profile_version: str = ""
    source_id: str = ""
    source_kind: str = ""
    # 只沿用保存結果中的 ranking metadata；不在觀察清單頁重新計算。
    sample_size: int | None = None
    score_percentile_bp: int | None = None
    ranking_method: str = ""
    calibrated_probability_bp: int | None = None
    calibrated_probability_status: str = "unavailable"
    after_cost_profit_probability_bp: int | None = None
    after_cost_profit_probability_status: str = "unavailable"
    confidence_tier: str = ""
    evidence_confidence: str = ""
    calibration_model_version: str = ""
    calibration_dataset_version: str = ""
    calibration_horizon: str = ""
    calibration_status: str = "unavailable"
    calibration_source: str = ""
    calibration_source_trace: tuple[str, ...] = ()
    calibration_warnings: tuple[str, ...] = ()
    cost_basis_bp: int | None = None
    calibration_probability_transform_id: str = ""
    calibration_probability_baseline_id: str = ""
    calibration_probability_baseline_kind: str = ""
    calibration_probability_baseline_probability_bp: int | None = None
    calibration_raw_probability_bp: int | None = None
    calibration_raw_after_cost_probability_bp: int | None = None


class WatchlistAnalysisService:
    def __init__(self, config):
        self.runs_dir = Path(config.output_root) / "recommendation" / "runs"

    def load_result(
        self,
        source_id: str = "",
        *,
        as_of_date: date | None = None,
    ) -> RecommendationResultDTO | None:
        """以既有 runs registry 唯讀載入完整保存結果。

        呼叫端若提供 ``as_of_date``，保存結果的決策日必須不晚於該日；
        這個檢查讓個股報告可以重用既有結果而不引入 look-ahead。
        """

        path = self._resolve_result_path(source_id)
        if path is None:
            return None
        result = RecommendationResultDTO.from_dict(
            json.loads(path.read_text(encoding="utf-8"))
        )
        if source_id and result.result_id != source_id:
            raise ValueError("推薦內容與指定來源 ID 不一致")
        if as_of_date is not None:
            cutoff = str(result.run_context.get("as_of_date") or "")
            if not cutoff or date.fromisoformat(cutoff) > as_of_date:
                return None
        return result

    def fetch(self, stock_code: str, source_id: str, as_of_date: date) -> WatchlistAnalysisDTO:
        result = self.load_result(source_id, as_of_date=as_of_date)
        if result is None:
            if not (self.runs_dir / "recommendation_runs.db").is_file():
                return WatchlistAnalysisDTO(stock_code, "missing", message="尚無已保存推薦分析；可到推薦分析產生並保存結果。")
            if self._resolve_result_path(source_id) is None:
                return WatchlistAnalysisDTO(
                    stock_code,
                    "missing",
                    result_id=source_id,
                    message="找不到對應的已保存推薦來源。",
                )
            return WatchlistAnalysisDTO(
                stock_code,
                "unavailable",
                result_id=source_id,
                message="分析日期缺失或晚於查詢日期，不能作為當下分析。",
            )
        if source_id and result.result_id != source_id:
            raise ValueError("推薦內容與指定來源 ID 不一致")
        run_context = result.run_context or {}
        cutoff = str(run_context.get("as_of_date") or "")
        data_date = str(run_context.get("data_date") or "")
        profile_id = str(
            run_context.get("profile_id")
            or result.config.get("profile_id")
            or ""
        )
        profile_version = str(
            run_context.get("profile_version")
            or result.config.get("profile_version")
            or ""
        )
        source_kind = str(run_context.get("source_kind") or "recommendation")
        source_lineage_id = str(run_context.get("source_id") or "")
        if not cutoff or date.fromisoformat(cutoff) > as_of_date:
            return WatchlistAnalysisDTO(
                stock_code,
                "unavailable",
                result_id=result.result_id,
                message="分析日期缺失或晚於查詢日期，不能作為當下分析。",
                decision_date=cutoff,
                data_date=data_date,
                profile_id=profile_id,
                profile_version=profile_version,
                source_id=source_lineage_id,
                source_kind=source_kind,
            )
        for recommendation in result.recommendations:
            if recommendation.stock_code == stock_code:
                return WatchlistAnalysisDTO(
                    stock_code, "saved", cutoff, result.result_id,
                    str(recommendation.total_score), str(recommendation.close_price),
                    recommendation.recommendation_reasons,
                    "已保存分析快照，非即時行情；評分沿用該次策略設定。",
                    decision_date=cutoff,
                    data_date=data_date,
                    profile_id=profile_id,
                    profile_version=profile_version,
                    source_id=source_lineage_id,
                    source_kind=source_kind,
                    sample_size=(
                        recommendation.sample_size
                        if recommendation.sample_size is not None
                        else recommendation.eligible_universe_size
                    ),
                    score_percentile_bp=recommendation.score_percentile_bp,
                    ranking_method=str(recommendation.ranking_method or ""),
                    calibrated_probability_bp=recommendation.calibrated_probability_bp,
                    calibrated_probability_status=recommendation.calibrated_probability_status,
                    after_cost_profit_probability_bp=recommendation.after_cost_profit_probability_bp,
                    after_cost_profit_probability_status=recommendation.after_cost_profit_probability_status,
                    evidence_confidence=recommendation.evidence_confidence,
                    calibration_model_version=recommendation.calibration_model_version,
                    calibration_dataset_version=recommendation.calibration_dataset_version,
                    calibration_horizon=recommendation.calibration_horizon,
                    calibration_status=recommendation.calibration_status,
                    calibration_source=recommendation.calibration_source,
                    calibration_source_trace=tuple(recommendation.calibration_source_trace),
                    calibration_warnings=tuple(recommendation.calibration_warnings),
                    cost_basis_bp=recommendation.cost_basis_bp,
                    calibration_probability_transform_id=recommendation.calibration_probability_transform_id,
                    calibration_probability_baseline_id=recommendation.calibration_probability_baseline_id,
                    calibration_probability_baseline_kind=recommendation.calibration_probability_baseline_kind,
                    calibration_probability_baseline_probability_bp=(
                        recommendation.calibration_probability_baseline_probability_bp
                    ),
                    calibration_raw_probability_bp=recommendation.calibration_raw_probability_bp,
                    calibration_raw_after_cost_probability_bp=(
                        recommendation.calibration_raw_after_cost_probability_bp
                    ),
                )
        return WatchlistAnalysisDTO(
            stock_code,
            "not_in_result",
            cutoff,
            result.result_id,
            decision_date=cutoff,
            data_date=data_date,
            profile_id=profile_id,
            profile_version=profile_version,
            source_id=source_lineage_id,
            source_kind=source_kind,
            message="這份推薦未包含此股票；未入選不等於看空，可查看主力流向或重新分析。",
        )

    def _resolve_result_path(self, source_id: str) -> Path | None:
        """只解析 runs registry 指向 runs_dir 內的保存檔，且關閉 SQLite。"""

        db_path = self.runs_dir / "recommendation_runs.db"
        if not db_path.is_file():
            return None
        with closing(sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)) as conn:
            conn.execute("PRAGMA query_only=ON")
            if source_id:
                row = conn.execute(
                    "SELECT data_path FROM runs WHERE result_id = ?",
                    (source_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT data_path FROM runs ORDER BY created_at DESC, result_id LIMIT 1"
                ).fetchone()
        if row is None:
            return None
        path = Path(row[0]).resolve()
        if not path.is_relative_to(self.runs_dir.resolve()):
            raise ValueError("推薦來源路徑超出保存目錄")
        return path
