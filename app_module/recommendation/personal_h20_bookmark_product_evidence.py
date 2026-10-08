"""將原收藏已核驗的單股研究投影為摘要；不讀目前模型或重新預測。"""

from app_module.recommendation.personal_h20_product_evidence import PersonalH20ProductEvidence
from app_module.recommendation.personal_h20_research_bookmark import PersonalH20ResearchBookmarkState
from app_module.recommendation.personal_h20_research_cohort import PersonalH20ResearchSelection


def project_personal_h20_bookmark_product_evidence(
    state: PersonalH20ResearchBookmarkState,
) -> PersonalH20ProductEvidence:
    """只接受 exact typed state；未知列不以舊預測值或現在時間補齊。"""
    if not isinstance(state, PersonalH20ResearchBookmarkState):
        raise TypeError("personal_h20_bookmark_verified_state_required")
    bookmark, cohort, row = state.bookmark, state.cohort, state.selected_row
    selected = PersonalH20ResearchSelection(
        cohort.manifest_sha256, cohort.candidate_id, cohort.contract_hash,
        cohort.cycle_id, row.symbol, row.sample_id, row.prediction_id, row.capture_sha256,
    )
    matches = tuple(item for item in cohort.rows if item.symbol == row.symbol)
    if (selected != bookmark.selected_row or matches != (row,)
            or cohort.decision_date != bookmark.decision_date
            or row.decision_date != bookmark.decision_date):
        raise ValueError("personal_h20_bookmark_evidence_identity_mismatch")
    model_text = {
        "enabled_same_contract": "目前模型與原收藏契約相同",
        "disabled": "目前個人模型停用；仍顯示原保存研究",
        "enabled_other_contract": "目前模型契約不同；仍顯示原保存研究",
    }.get(state.current_model_binding_status)
    if model_text is None:
        raise ValueError("personal_h20_bookmark_model_status_invalid")
    if row.status == "unknown":
        if row.gross_return_bp is not None:
            raise ValueError("personal_h20_bookmark_unknown_row_has_prediction")
        return PersonalH20ProductEvidence(
            stock_code=row.symbol, status="unavailable", reason=row.reason,
            decision_date=row.decision_date,
        )
    if row.status != "available":
        raise ValueError("personal_h20_bookmark_row_status_invalid")
    return PersonalH20ProductEvidence(
        stock_code=row.symbol, status="available",
        reason=f"{model_text}；{row.reason}",
        gross_return_bp=row.gross_return_bp, decision_date=row.decision_date,
        source_date=row.source_date, feature_date=row.feature_as_of_date,
        observed_at=row.observed_at, candidate_id=cohort.candidate_id,
        sample_id=row.sample_id, prediction_id=row.prediction_id,
    )
