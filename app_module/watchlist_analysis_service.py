"""觀察清單的唯讀已保存個股分析，不重新評分或改寫來源。"""
from dataclasses import dataclass
from collections.abc import Mapping
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app_module.recommendation.contracts import ExecutionStatus, ReferenceKind
from app_module.recommendation.queries import RecommendationExecutionReadModel
from app_module.saved_recommendation_queries import (
    build_recommendation_execution_queries,
    execution_result_config,
    canonical_scheduled_decision_date,
    saved_recommendation_capture_projection,
    recommendation_runs_dir,
    verified_saved_calibration_projections,
)

_TAIPEI = ZoneInfo("Asia/Taipei")


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
    source_snapshot_id: str = ""
    source_snapshot_hash: str = ""
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
    def __init__(self, config, *, queries=None, clock=None):
        self.runs_dir = recommendation_runs_dir(config)
        self.queries = queries or build_recommendation_execution_queries(config)
        self.clock = clock or (lambda: datetime.now(_TAIPEI))

    def load_result(
        self,
        source_id: str = "",
        *,
        as_of_date: date | None = None,
    ) -> RecommendationExecutionReadModel | None:
        """以統一 query 唯讀載入明確指定的保存結果。

        呼叫端若提供 ``as_of_date``，保存結果的決策日必須不晚於該日；
        這個檢查讓個股報告可以重用既有結果而不引入 look-ahead。
        """

        source_key = str(source_id or "").strip()
        # 空 source 代表 caller 沒有選定原始推薦；不可退回 registry 的
        # latest row，否則同股不同 result 會被錯誤串接成目前來源。
        if not source_key:
            return None
        result = self.queries.get(source_key)
        if result is None:
            return None
        if result.result_id != source_key:
            raise ValueError("推薦內容與指定來源 ID 不一致")
        if as_of_date is not None:
            cutoff = _result_as_of_date(result)
            if cutoff is None or cutoff > as_of_date:
                return None
        return result

    def fetch(self, stock_code: str, source_id: str, as_of_date: date) -> WatchlistAnalysisDTO:
        source_key = str(source_id or "").strip()
        if not source_key:
            return WatchlistAnalysisDTO(
                stock_code,
                "missing",
                message=(
                    "尚未選定原始推薦來源；不會以同股或最新結果猜測。"
                    "請回到推薦分析保存結果，或明確選擇原始推薦來源。"
                ),
            )
        result = self.queries.get(source_key)
        if result is None:
            if not (self.runs_dir / "recommendation_runs.db").is_file():
                return WatchlistAnalysisDTO(stock_code, "missing", message="尚無已保存推薦分析；可到推薦分析產生並保存結果。")
            return WatchlistAnalysisDTO(
                stock_code,
                "missing",
                source_id=source_key,
                message="找不到對應的已保存推薦來源。",
            )
        result_as_of_date = _result_as_of_date(result)
        if result_as_of_date is None or result_as_of_date > as_of_date:
            return WatchlistAnalysisDTO(
                stock_code,
                "unavailable",
                source_id=source_key,
                message="分析日期缺失或晚於查詢日期，不能作為當下分析。",
            )
        if result.result_id != source_key:
            raise ValueError("推薦內容與指定來源 ID 不一致")
        legacy = result.legacy_result
        execution = result.execution
        if legacy is not None:
            run_context = legacy.run_context or {}
            config_values = legacy.config or {}
            cutoff = str(run_context.get("as_of_date") or "")
            data_date = str(run_context.get("data_date") or "")
            profile_id = str(run_context.get("profile_id") or config_values.get("profile_id") or "")
            profile_version = str(run_context.get("profile_version") or config_values.get("profile_version") or "")
            source_kind = str(run_context.get("source_kind") or "recommendation")
            source_lineage_id = str(run_context.get("source_id") or "")
            source_snapshot_id = str(
                run_context.get("source_snapshot_id")
                or config_values.get("source_snapshot_id")
                or ""
            )
            source_snapshot_hash = str(
                run_context.get("source_snapshot_hash")
                or config_values.get("source_snapshot_hash")
                or ""
            )
            recommendations = legacy.recommendations
            calibrations = {}
        elif execution is not None:
            if execution.status is not ExecutionStatus.COMPLETED or execution.decision is None:
                return WatchlistAnalysisDTO(
                    stock_code,
                    "unavailable",
                    result_id=result.result_id,
                    source_id=source_key,
                    message="保存結果沒有 completed 決策資料，未以其他結果或解碼器回退。",
                )
            context = execution.context
            config_values = execution_result_config(execution)
            cutoff = context.as_of_date.isoformat() if context.as_of_date is not None else ""
            if config_values.get("scheduled_snapshot") is True:
                cutoff = canonical_scheduled_decision_date(result) or ""
                data_date = context.as_of_date.isoformat() if context.as_of_date else ""
            else:
                data_date = _current_execution_data_date(
                    execution,
                    stock_code=stock_code,
                    expected_result_id=result.result_id,
                    result_as_of_date=result_as_of_date,
                )
            profile_id = str(
                config_values.get("profile_id")
                or (context.profile_ref.reference_id if context.profile_ref is not None else "")
            )
            profile_version = str(
                config_values.get("profile_version")
                or (context.profile_ref.version if context.profile_ref is not None and context.profile_ref.version else "")
            )
            source_ids = tuple(dict.fromkeys(item.source_id for item in context.source_refs))
            snapshot_ids = tuple(
                dict.fromkeys(item.snapshot_id for item in context.source_refs if item.snapshot_id)
            )
            source_lineage_id = source_ids[0] if len(source_ids) == 1 else ""
            source_snapshot_id = snapshot_ids[0] if len(snapshot_ids) == 1 else ""
            source_kind = ""
            source_snapshot_hash = ""
            recommendations = execution.decision.items if execution.decision is not None else ()
            calibrations = verified_saved_calibration_projections(result)
        else:
            return WatchlistAnalysisDTO(
                stock_code,
                "unavailable",
                result_id=source_key,
                source_id=source_key,
                message="保存結果格式不支援，未以其他 decoder 回退。",
            )
        if not cutoff or result_as_of_date is None or result_as_of_date > as_of_date:
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
                source_snapshot_id=source_snapshot_id,
                source_snapshot_hash=source_snapshot_hash,
            )
        if data_date:
            try:
                parsed_data_date = date.fromisoformat(data_date)
            except ValueError:
                data_date_problem = (
                    f"保存來源市場資料日格式無效：{data_date!r}；拒絕讀取。"
                )
            else:
                if parsed_data_date.isoformat() != data_date:
                    data_date_problem = (
                        f"保存來源市場資料日格式無效：{data_date!r}；拒絕讀取。"
                    )
                elif (
                    result_as_of_date is not None
                    and parsed_data_date > result_as_of_date
                ):
                    data_date_problem = (
                        f"保存來源市場資料日 {data_date} 晚於來源決策／as-of 日期 "
                        f"{result_as_of_date.isoformat()}；拒絕讀取。"
                    )
                elif parsed_data_date > as_of_date:
                    data_date_problem = (
                        f"保存來源市場資料日 {data_date} 晚於查詢截止日 "
                        f"{as_of_date.isoformat()}；拒絕讀取。"
                    )
                else:
                    data_date_problem = ""
            if data_date_problem:
                return WatchlistAnalysisDTO(
                    stock_code,
                    "unavailable",
                    result_id=result.result_id,
                    message=data_date_problem,
                    decision_date=cutoff,
                    data_date=data_date,
                    profile_id=profile_id,
                    profile_version=profile_version,
                    source_id=source_lineage_id,
                    source_kind=source_kind,
                    source_snapshot_id=source_snapshot_id,
                    source_snapshot_hash=source_snapshot_hash,
                )
        for recommendation in recommendations:
            if recommendation.stock_code == stock_code:
                calibration = calibrations.get(stock_code)
                if legacy is not None:
                    total_score = recommendation.total_score
                    close_price = recommendation.close_price
                    reasons = recommendation.recommendation_reasons
                    sample_size = (
                        recommendation.sample_size
                        if recommendation.sample_size is not None
                        else recommendation.eligible_universe_size
                    )
                    score_percentile_bp = recommendation.score_percentile_bp
                    ranking_method = str(recommendation.ranking_method or "")
                else:
                    total_score = recommendation.rule_score
                    close_price = recommendation.close_price
                    reasons = recommendation.reason_text or "; ".join(recommendation.reasons)
                    sample_size = calibration.sample_size if calibration is not None else recommendation.eligible_universe_size
                    score_percentile_bp = recommendation.score_percentile_bp
                    ranking_method = recommendation.ranking_method or ""
                return WatchlistAnalysisDTO(
                    stock_code, "saved", cutoff, result.result_id,
                    "" if total_score is None else str(total_score),
                    "" if close_price is None else str(close_price),
                    reasons or "",
                    "已保存分析快照，非即時行情；評分沿用該次策略設定。",
                    decision_date=cutoff,
                    data_date=data_date,
                    profile_id=profile_id,
                    profile_version=profile_version,
                    source_id=source_lineage_id,
                    source_kind=source_kind,
                    source_snapshot_id=source_snapshot_id,
                    source_snapshot_hash=source_snapshot_hash,
                    sample_size=sample_size,
                    score_percentile_bp=score_percentile_bp,
                    ranking_method=ranking_method,
                    calibrated_probability_bp=(recommendation.calibrated_probability_bp if legacy is not None else (calibration.calibrated_probability_bp if calibration is not None else None)),
                    calibrated_probability_status=(recommendation.calibrated_probability_status if legacy is not None else (calibration.calibrated_probability_status if calibration is not None else "unavailable")),
                    after_cost_profit_probability_bp=(recommendation.after_cost_profit_probability_bp if legacy is not None else (calibration.after_cost_profit_probability_bp if calibration is not None else None)),
                    after_cost_profit_probability_status=(recommendation.after_cost_profit_probability_status if legacy is not None else (calibration.after_cost_profit_probability_status if calibration is not None else "unavailable")),
                    confidence_tier=(calibration.confidence_tier if legacy is None and calibration is not None else ""),
                    evidence_confidence=(recommendation.evidence_confidence if legacy is not None else (calibration.evidence_confidence if calibration is not None else "")),
                    calibration_model_version=(recommendation.calibration_model_version if legacy is not None else (calibration.model_version if calibration is not None else "")),
                    calibration_dataset_version=(recommendation.calibration_dataset_version if legacy is not None else (calibration.dataset_version if calibration is not None else "")),
                    calibration_horizon=(recommendation.calibration_horizon if legacy is not None else (calibration.horizon if calibration is not None else "")),
                    calibration_status=(recommendation.calibration_status if legacy is not None else (calibration.status if calibration is not None else "unavailable")),
                    calibration_source=(recommendation.calibration_source if legacy is not None else (calibration.source_trace[0] if calibration is not None and calibration.source_trace else "")),
                    calibration_source_trace=(tuple(recommendation.calibration_source_trace) if legacy is not None else (calibration.source_trace if calibration is not None else ())),
                    calibration_warnings=(tuple(recommendation.calibration_warnings) if legacy is not None else (calibration.warnings if calibration is not None else ())),
                    cost_basis_bp=(recommendation.cost_basis_bp if legacy is not None else (calibration.cost_basis_bp if calibration is not None else None)),
                    calibration_probability_transform_id=(recommendation.calibration_probability_transform_id if legacy is not None else (calibration.probability_transform_id if calibration is not None else "")),
                    calibration_probability_baseline_id=(recommendation.calibration_probability_baseline_id if legacy is not None else (calibration.probability_baseline_id if calibration is not None else "")),
                    calibration_probability_baseline_kind=(recommendation.calibration_probability_baseline_kind if legacy is not None else (calibration.probability_baseline_kind if calibration is not None else "")),
                    calibration_probability_baseline_probability_bp=(recommendation.calibration_probability_baseline_probability_bp if legacy is not None else (calibration.probability_baseline_probability_bp if calibration is not None else None)),
                    calibration_raw_probability_bp=(recommendation.calibration_raw_probability_bp if legacy is not None else (calibration.raw_calibrated_probability_bp if calibration is not None else None)),
                    calibration_raw_after_cost_probability_bp=(recommendation.calibration_raw_after_cost_probability_bp if legacy is not None else (calibration.raw_after_cost_profit_probability_bp if calibration is not None else None)),
                )
        capture = saved_recommendation_capture_projection(result)
        screening = capture.get("screening_matrix_json") or ()
        if isinstance(screening, str):
            import json
            screening = json.loads(screening)
        if not isinstance(screening, (list, tuple)):
            raise ValueError("保存篩選矩陣必須是逐列清單")
        rows = [row for row in screening if isinstance(row, Mapping) and str(row.get("stock_code") or "") == stock_code]
        if len(rows) > 1:
            raise ValueError("指定股票在保存篩選矩陣出現重複列")
        exclusion_reasons = ""
        if rows:
            reasons = rows[0].get("reason_codes") or ()
            exclusion_reasons = "；".join(str(reason) for reason in reasons)
            if not exclusion_reasons:
                exclusion_reasons = str(rows[0].get("status") or "未入選")
        return WatchlistAnalysisDTO(
            stock_code,
            "not_in_result",
            cutoff,
            result.result_id,
            reasons=exclusion_reasons,
            decision_date=cutoff,
            data_date=data_date,
            profile_id=profile_id,
            profile_version=profile_version,
            source_id=source_lineage_id,
            source_kind=source_kind,
            source_snapshot_id=source_snapshot_id,
            source_snapshot_hash=source_snapshot_hash,
            message=("此股已在這份保存結果中接受篩選，未入選原因："+exclusion_reasons+"；不等於看空。") if rows else "這份推薦未包含此股票；未入選不等於看空，可查看主力流向或重新分析。",
        )

    def list_saved_sources(
        self,
        stock_code: str = "",
        *,
        as_of_date: date | None = None,
    ) -> list[dict[str, str]]:
        """列出明確選取來源；指定股票時只列同股決策或明列篩選列。

        清單篩選只用來避免使用者把其他股票的 run 綁到目前候選；真正
        綁定前仍須用實際查詢日期呼叫 ``fetch`` 再驗一次日期與來源完整性。
        """

        code = str(stock_code or "").strip()
        options: list[dict[str, str]] = []
        for item in self.queries.list():
            result_id = str(item.result_id or "").strip()
            if not result_id:
                continue
            option = {
                "result_id": result_id,
                "result_name": (
                    item.legacy_result.result_name
                    if item.legacy_result is not None
                    else item.label or ""
                ),
                "created_at": _result_created_at(item),
            }
            if code:
                cutoff = as_of_date or self._today_taipei()
                analysis = self.fetch(code, result_id, cutoff)
                if analysis.result_id != result_id or analysis.stock_code != code:
                    continue
                if analysis.status == "saved":
                    option["membership_status"] = "saved"
                elif analysis.status == "not_in_result" and analysis.reasons.strip():
                    # 保存矩陣明列此股未入選時，允許追溯該排除紀錄；它不會
                    # 被提升成推薦，watchlist/report 仍使用 not_in_result 狀態。
                    option["membership_status"] = "not_in_result"
                    option["screening_reason"] = analysis.reasons
                else:
                    continue
                option["decision_date"] = analysis.decision_date
                option["data_date"] = analysis.data_date
                option["source_id"] = analysis.source_id
                option["source_snapshot_id"] = analysis.source_snapshot_id
                option["source_snapshot_hash"] = analysis.source_snapshot_hash
            options.append(option)
        return options

    def _today_taipei(self) -> date:
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("watchlist source clock must include a timezone")
        return now.astimezone(_TAIPEI).date()


def _result_as_of_date(read_model: RecommendationExecutionReadModel) -> date | None:
    if read_model.legacy_result is not None:
        value = str(read_model.legacy_result.run_context.get("as_of_date") or "")
        try:
            return date.fromisoformat(value) if value else None
        except ValueError:
            return None
    if read_model.execution is not None:
        if execution_result_config(read_model.execution).get("scheduled_snapshot") is True:
            day = canonical_scheduled_decision_date(read_model)
            return date.fromisoformat(day) if day else None
        return read_model.execution.context.as_of_date
    return None


def _current_execution_data_date(
    execution: object,
    *,
    stock_code: str,
    expected_result_id: str,
    result_as_of_date: date | None,
) -> str:
    """Project a quote date only from exact same-execution provenance."""

    if result_as_of_date is None or type(expected_result_id) is not str:
        return ""
    if getattr(execution, "result_id", None) != expected_result_id:
        return ""
    if type(stock_code) is not str or not stock_code.strip():
        return ""
    context = getattr(execution, "context", None)
    if context is None or getattr(context, "as_of_date", None) != result_as_of_date:
        return ""
    decision_at = getattr(context, "decision_at", None)
    if decision_at is not None and (
        not isinstance(decision_at, datetime)
        or decision_at.tzinfo is None
        or decision_at.utcoffset() is None
    ):
        return ""
    decision = getattr(execution, "decision", None)
    if decision is None:
        return ""
    decision_items = getattr(decision, "items", ())
    decision_assessments = getattr(decision, "assessments", ())
    if not isinstance(decision_items, (tuple, list)) or not isinstance(
        decision_assessments, (tuple, list)
    ):
        return ""
    decision_rows = (
        *decision_items,
        *decision_assessments,
    )
    if not any(getattr(row, "stock_code", None) == stock_code for row in decision_rows):
        return ""

    events = getattr(execution, "events", ())
    if not isinstance(events, (tuple, list)):
        return ""
    lineage_events = tuple(
        event
        for event in events
        if getattr(event, "event_type", None) == "current_fundamental_lineage"
    )
    invocation_events = tuple(
        event
        for event in events
        if getattr(event, "event_type", None) == "legacy_invocation_context"
    )
    if len(lineage_events) > 1 or len(invocation_events) > 1:
        return ""

    provenance_event = invocation_events[0] if invocation_events else None
    provenance_details = (
        getattr(provenance_event, "details", None)
        if provenance_event is not None
        else None
    )
    if isinstance(provenance_details, Mapping) and (
        "market_data_provenance" in provenance_details
    ):
        provenance_date, provenance_scope = _market_data_provenance_date(
            provenance_event,
            provenance_details,
            context=context,
            expected_result_id=expected_result_id,
            result_as_of_date=result_as_of_date,
        )
        if provenance_date is None or provenance_scope is None:
            return ""
        if provenance_scope == "natural_current_observation":
            if len(lineage_events) != 1:
                return ""
            lineage_date = _current_lineage_data_date(
                lineage_events[0],
                execution=execution,
                context=context,
                decision_at=decision_at,
                expected_result_id=expected_result_id,
                result_as_of_date=result_as_of_date,
                expected_provenance=provenance_details["market_data_provenance"],
            )
            if lineage_date is None or lineage_date != provenance_date:
                return ""
        elif lineage_events:
            return ""
        return provenance_date.isoformat()

    if len(lineage_events) != 1:
        return ""
    lineage_date = _current_lineage_data_date(
        lineage_events[0],
        execution=execution,
        context=context,
        decision_at=decision_at,
        expected_result_id=expected_result_id,
        result_as_of_date=result_as_of_date,
    )
    return lineage_date.isoformat() if lineage_date is not None else ""


def _market_data_provenance_date(
    event: object,
    event_details: Mapping[str, object],
    *,
    context: object,
    expected_result_id: str,
    result_as_of_date: date,
) -> tuple[date | None, str | None]:
    provenance = event_details.get("market_data_provenance")
    required_fields = {
        "schema_version",
        "result_id",
        "invocation_id",
        "scope",
        "as_of_date",
        "data_date",
        "decision_at",
        "source_id",
        "market_data_fingerprint",
    }
    if not isinstance(provenance, Mapping) or not required_fields.issubset(provenance):
        return None, None
    scope = provenance.get("scope")
    if (
        provenance.get("schema_version")
        != "recommendation-market-data-provenance.v1"
        or type(scope) is not str
        or scope not in {"natural_current_observation", "formal_pit"}
        or provenance.get("result_id") != expected_result_id
        or event_details.get("result_id") != expected_result_id
    ):
        return None, None
    invocation_id = provenance.get("invocation_id")
    invocation_prefix = f"{expected_result_id}:"
    if (
        type(invocation_id) is not str
        or not invocation_id.startswith(invocation_prefix)
        or len(invocation_id) != len(invocation_prefix) + 32
        or any(
            character not in "0123456789abcdef"
            for character in invocation_id[len(invocation_prefix) :]
        )
    ):
        return None, None
    if event_details.get("invocation_id") != invocation_id:
        return None, None
    if provenance.get("as_of_date") != result_as_of_date.isoformat():
        return None, None
    market_date = _parse_canonical_lineage_date(provenance.get("data_date"))
    if market_date is None or market_date > result_as_of_date:
        return None, None

    decision_at = getattr(context, "decision_at", None)
    provenance_decision_at = provenance.get("decision_at")
    if provenance_decision_at is None:
        if decision_at is not None:
            return None, None
    else:
        parsed_decision_at = _parse_aware_lineage_datetime(provenance_decision_at)
        if (
            parsed_decision_at is None
            or not isinstance(decision_at, datetime)
            or decision_at.tzinfo is None
            or decision_at.utcoffset() is None
            or parsed_decision_at.astimezone(timezone.utc)
            != decision_at.astimezone(timezone.utc)
        ):
            return None, None

    source_id = provenance.get("source_id")
    market_fingerprint = provenance.get("market_data_fingerprint")
    if (
        type(source_id) is not str
        or not source_id.strip()
        or event_details.get("source_id") != source_id
        or not _is_raw_sha256_digest(market_fingerprint)
        or event_details.get("market_data_fingerprint") != market_fingerprint
    ):
        return None, None
    return market_date, scope


def _current_lineage_data_date(
    event: object,
    *,
    execution: object,
    context: object,
    decision_at: object,
    expected_result_id: str,
    result_as_of_date: date,
    expected_provenance: Mapping[str, object] | None = None,
) -> date | None:
    details = getattr(event, "details", None)
    required_fields = {
        "schema_version",
        "result_id",
        "invocation_id",
        "scope",
        "as_of_date",
        "data_date",
        "expected_market_date",
        "market_calendar_status",
        "decision_at",
        "current_observation_cutoff_at",
        "source_id",
        "market_data_fingerprint",
        "data_fingerprint",
    }
    if not isinstance(details, Mapping) or not required_fields.issubset(details):
        return None
    if (
        details.get("schema_version")
        != "recommendation-current-fundamental-lineage.v1"
        or details.get("scope") != "natural_current_observation"
        or details.get("result_id") != expected_result_id
    ):
        return None

    invocation_id = details.get("invocation_id")
    invocation_prefix = f"{expected_result_id}:"
    if (
        type(invocation_id) is not str
        or not invocation_id.startswith(invocation_prefix)
        or len(invocation_id) != len(invocation_prefix) + 32
        or any(character not in "0123456789abcdef" for character in invocation_id[len(invocation_prefix) :])
    ):
        return None

    as_of_text = result_as_of_date.isoformat()
    if details.get("as_of_date") != as_of_text:
        return None
    event_decision_at = _parse_aware_lineage_datetime(details.get("decision_at"))
    observation_cutoff_at = _parse_aware_lineage_datetime(
        details.get("current_observation_cutoff_at")
    )
    if (
        event_decision_at is None
        or observation_cutoff_at is None
        or not isinstance(decision_at, datetime)
        or decision_at.tzinfo is None
        or decision_at.utcoffset() is None
        or event_decision_at.astimezone(timezone.utc)
        != decision_at.astimezone(timezone.utc)
        or observation_cutoff_at.astimezone(timezone.utc)
        > event_decision_at.astimezone(timezone.utc)
    ):
        return None
    occurred_at = getattr(event, "occurred_at", None)
    if (
        not isinstance(occurred_at, datetime)
        or occurred_at.tzinfo is None
        or occurred_at.utcoffset() is None
        or occurred_at.astimezone(timezone.utc)
        != event_decision_at.astimezone(timezone.utc)
    ):
        return None

    market_date = _parse_canonical_lineage_date(details.get("data_date"))
    if market_date is None or market_date > result_as_of_date:
        return None
    if expected_provenance is not None:
        provenance_date = _parse_canonical_lineage_date(
            expected_provenance.get("data_date")
        )
        provenance_decision_at = _parse_aware_lineage_datetime(
            expected_provenance.get("decision_at")
        )
        if (
            details.get("result_id") != expected_provenance.get("result_id")
            or details.get("invocation_id")
            != expected_provenance.get("invocation_id")
            or details.get("scope") != expected_provenance.get("scope")
            or details.get("as_of_date")
            != expected_provenance.get("as_of_date")
            or details.get("data_date") != expected_provenance.get("data_date")
            or provenance_date != market_date
            or details.get("source_id") != expected_provenance.get("source_id")
            or details.get("market_data_fingerprint")
            != expected_provenance.get("market_data_fingerprint")
            or (
                details.get("decision_at") is None
                and expected_provenance.get("decision_at") is not None
            )
            or (
                details.get("decision_at") is not None
                and (
                    provenance_decision_at is None
                    or event_decision_at.astimezone(timezone.utc)
                    != provenance_decision_at.astimezone(timezone.utc)
                )
            )
        ):
            return None
    expected_market_date = details.get("expected_market_date")
    parsed_expected_date = (
        _parse_canonical_lineage_date(expected_market_date)
        if expected_market_date is not None
        else None
    )
    if expected_market_date is not None and parsed_expected_date is None:
        return None
    if parsed_expected_date is not None and parsed_expected_date > result_as_of_date:
        return None

    market_status = details.get("market_calendar_status")
    if market_status == "current":
        if parsed_expected_date is None or market_date != parsed_expected_date:
            return None
    elif market_status == "stale":
        if parsed_expected_date is None or market_date >= parsed_expected_date:
            return None
    elif market_status is None:
        if parsed_expected_date is not None:
            return None
    else:
        return None

    source_id = details.get("source_id")
    market_fingerprint = details.get("market_data_fingerprint")
    data_fingerprint = details.get("data_fingerprint")
    if (
        type(source_id) is not str
        or not source_id.strip()
        or not _is_raw_sha256_digest(market_fingerprint)
        or not _is_raw_sha256_digest(data_fingerprint)
    ):
        return None
    snapshot_refs = getattr(context, "data_snapshot_refs", ())
    if not isinstance(snapshot_refs, (tuple, list)) or len(snapshot_refs) != 1:
        return None
    reference = snapshot_refs[0]
    if (
        getattr(reference, "kind", None) is not ReferenceKind.DATA_SNAPSHOT
        or getattr(reference, "reference_id", None) != market_fingerprint
        or getattr(reference, "version", None)
        != f"{source_id}:{market_date.isoformat()}"
    ):
        return None
    return market_date


def _parse_aware_lineage_datetime(value: object) -> datetime | None:
    if type(value) is not str or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _parse_canonical_lineage_date(value: object) -> date | None:
    if type(value) is not str:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _is_raw_sha256_digest(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _result_created_at(read_model: RecommendationExecutionReadModel) -> str:
    if read_model.legacy_result is not None:
        return read_model.legacy_result.created_at or ""
    if read_model.execution is not None and read_model.execution.context.created_at is not None:
        return read_model.execution.context.created_at.isoformat()
    return ""
