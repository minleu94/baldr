"""Pure reducer for research-session events."""

from dataclasses import replace

from .session_dtos import ResearchSessionSnapshotDTO
from .session_events import (
    ActiveProfileChanged,
    ActiveRegimeChanged,
    ActiveSymbolChanged,
    CurrentRecommendationRunChanged,
    ResearchSessionEvent,
    SelectedWatchlistChanged,
    StockResearchContextChanged,
)
from .session_dtos import ResearchStockContextDTO


def reduce_session_event(
    snapshot: ResearchSessionSnapshotDTO,
    event: ResearchSessionEvent,
) -> ResearchSessionSnapshotDTO:
    """Return a new snapshot for a session event."""

    if isinstance(event, ActiveSymbolChanged):
        return replace(snapshot, active_symbol=_normalize(event.symbol))
    if isinstance(event, ActiveRegimeChanged):
        return replace(snapshot, active_regime=_normalize(event.regime))
    if isinstance(event, ActiveProfileChanged):
        return replace(snapshot, active_profile=_normalize(event.profile))
    if isinstance(event, SelectedWatchlistChanged):
        return replace(snapshot, selected_watchlist_id=_normalize(event.watchlist_id))
    if isinstance(event, CurrentRecommendationRunChanged):
        return replace(snapshot, current_recommendation_run_id=_normalize(event.run_id))
    if isinstance(event, StockResearchContextChanged):
        supplied_context = event.context
        stock_code = _normalize(
            supplied_context.stock_code if supplied_context is not None else event.stock_code
        )
        if stock_code is None:
            return replace(
                snapshot,
                active_symbol=None,
                active_stock_code=None,
                stock_context=None,
                decision_date=None,
                data_date=None,
                result_id=None,
                identity_status=None,
                source_snapshot_id=None,
                source_snapshot_hash=None,
                profile_id=None,
                profile_version=None,
                source_id=None,
                source_version=None,
                mapping_source_id=None,
                mapping_version=None,
                mapping_observed_date=None,
                source_kind=None,
                source_label=None,
                source_workspace=None,
                ml_scope_mode=None,
                daily_snapshot_root=None,
                daily_snapshot_cohort_id=None,
                daily_snapshot_condition_keys=None,
                daily_snapshot_combine_mode=None,
                active_profile=None,
            )
        context = ResearchStockContextDTO(
            stock_code=stock_code,
            stock_name=_normalize(
                supplied_context.stock_name if supplied_context is not None else event.stock_name
            ) or "",
            decision_date=_normalize(
                supplied_context.decision_date if supplied_context is not None else event.decision_date
            ) or "",
            data_date=_normalize(
                supplied_context.data_date if supplied_context is not None else event.data_date
            ) or "",
            result_id=_normalize(
                supplied_context.result_id if supplied_context is not None else event.result_id
            ) or "",
            identity_status=_normalize(
                supplied_context.identity_status
                if supplied_context is not None
                else event.identity_status
            ) or "",
            source_snapshot_id=_normalize(
                supplied_context.source_snapshot_id
                if supplied_context is not None
                else event.source_snapshot_id
            ) or "",
            source_snapshot_hash=_normalize(
                supplied_context.source_snapshot_hash
                if supplied_context is not None
                else event.source_snapshot_hash
            ) or "",
            profile_id=_normalize(
                supplied_context.profile_id if supplied_context is not None else event.profile_id
            ) or "",
            profile_version=_normalize(
                supplied_context.profile_version if supplied_context is not None else event.profile_version
            ) or "",
            source_id=_normalize(
                supplied_context.source_id if supplied_context is not None else event.source_id
            ) or "",
            source_version=_normalize(
                supplied_context.source_version if supplied_context is not None else event.source_version
            ) or "",
            mapping_source_id=_normalize(
                supplied_context.mapping_source_id if supplied_context is not None else event.mapping_source_id
            ) or "",
            mapping_version=_normalize(
                supplied_context.mapping_version if supplied_context is not None else event.mapping_version
            ) or "",
            mapping_observed_date=_normalize(
                supplied_context.mapping_observed_date
                if supplied_context is not None
                else event.mapping_observed_date
            ) or "",
            source_kind=_normalize(
                supplied_context.source_kind if supplied_context is not None else event.source_kind
            ) or "",
            source_label=_normalize(
                supplied_context.source_label if supplied_context is not None else event.source_label
            ) or "",
            source_workspace=_normalize(
                supplied_context.source_workspace if supplied_context is not None else event.source_workspace
            ) or "",
            ml_scope_mode=_normalize(
                supplied_context.ml_scope_mode
                if supplied_context is not None
                else event.ml_scope_mode
            ) or "",
            daily_snapshot_root=_normalize(
                supplied_context.daily_snapshot_root
                if supplied_context is not None
                else event.daily_snapshot_root
            ) or "",
            daily_snapshot_cohort_id=_normalize(
                supplied_context.daily_snapshot_cohort_id
                if supplied_context is not None
                else event.daily_snapshot_cohort_id
            ) or "",
            daily_snapshot_condition_keys=_normalize(
                supplied_context.daily_snapshot_condition_keys
                if supplied_context is not None
                else event.daily_snapshot_condition_keys
            ) or "",
            daily_snapshot_combine_mode=_normalize(
                supplied_context.daily_snapshot_combine_mode
                if supplied_context is not None
                else event.daily_snapshot_combine_mode
            ) or "",
            rank_context=(
                supplied_context.rank_context
                if supplied_context is not None
                else event.rank_context
            ),
        )
        return replace(
            snapshot,
            active_symbol=stock_code,
            active_stock_code=stock_code,
            active_profile=context.profile_id or None,
            current_recommendation_run_id=context.result_id or None,
            stock_context=context,
            decision_date=context.decision_date or None,
            data_date=context.data_date or None,
            result_id=context.result_id or None,
            identity_status=context.identity_status or None,
            source_snapshot_id=context.source_snapshot_id or None,
            source_snapshot_hash=context.source_snapshot_hash or None,
            profile_id=context.profile_id or None,
            profile_version=context.profile_version or None,
            source_id=context.source_id or None,
            source_version=context.source_version or None,
            mapping_source_id=context.mapping_source_id or None,
            mapping_version=context.mapping_version or None,
            mapping_observed_date=context.mapping_observed_date or None,
            source_kind=context.source_kind or None,
            source_label=context.source_label or None,
            source_workspace=context.source_workspace or None,
            ml_scope_mode=context.ml_scope_mode or None,
            daily_snapshot_root=context.daily_snapshot_root or None,
            daily_snapshot_cohort_id=context.daily_snapshot_cohort_id or None,
            daily_snapshot_condition_keys=context.daily_snapshot_condition_keys or None,
            daily_snapshot_combine_mode=context.daily_snapshot_combine_mode or None,
        )

    return snapshot


def _normalize(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None
