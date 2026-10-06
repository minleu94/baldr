from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from app_module.daily_market_research_presets import (
    DAILY_MARKET_RESEARCH_PRESETS,
    ResearchCandidateSummary,
    get_research_filter_preset,
    match_research_filter_preset,
    summarize_research_candidates,
)


_BOTH = ("close_above_ma20", "close_above_ma60")


@dataclass(frozen=True)
class _Condition:
    key: str
    state: str
    reason: str = ""
    unknown_reason: str | None = None


@dataclass(frozen=True)
class _Row:
    stock_code: str
    combined_state: str
    why_not: tuple[str, ...] = ()
    conditions: tuple[_Condition, ...] = ()


def _snapshot(
    declared: tuple[str, ...], published: tuple[str, ...]
) -> SimpleNamespace:
    return SimpleNamespace(
        manifest={"declared_stock_codes": list(declared)},
        stock_snapshots={code: {"stock_code": code} for code in published},
    )


def test_presets_keep_existing_conditions_and_three_state_semantics() -> None:
    presets = {preset.preset_id: preset for preset in DAILY_MARKET_RESEARCH_PRESETS}

    assert presets["all_observations"].condition_keys == _BOTH
    assert presets["all_observations"].combine_mode == "AND"
    assert presets["all_observations"].filter_state == "all"
    assert presets["any_above"].condition_keys == _BOTH
    assert presets["any_above"].combine_mode == "OR"
    assert presets["any_above"].filter_state == "match"
    assert presets["ma20_above"].condition_keys == ("close_above_ma20",)
    assert presets["ma20_above"].combine_mode == "AND"
    assert presets["ma60_above"].condition_keys == ("close_above_ma60",)
    assert presets["ma60_above"].combine_mode == "AND"
    assert presets["needs_review"].condition_keys == _BOTH
    assert presets["needs_review"].combine_mode == "AND"
    assert presets["needs_review"].filter_state == "unknown"


def test_preset_lookup_rejects_unknown_ids_and_match_preserves_custom_filters() -> None:
    assert get_research_filter_preset("any_above").preset_id == "any_above"
    with pytest.raises(ValueError, match="未知"):
        get_research_filter_preset("made_up")

    assert match_research_filter_preset(_BOTH, "OR", "match") == "any_above"
    assert match_research_filter_preset(list(_BOTH), "AND", "all") == "all_observations"
    assert match_research_filter_preset((_BOTH[1], _BOTH[0]), "AND", "all") is None
    assert match_research_filter_preset(("custom_condition",), "AND", "match") is None
    assert match_research_filter_preset(_BOTH, "OR", "unknown") is None


def test_summary_uses_declared_denominator_without_creating_missing_rows() -> None:
    snapshot = _snapshot(("1101", "1477", "2382", "2603"), ("1101", "1477", "2382"))
    rows = (
        _Row("1101", "match", why_not=()),
        _Row("1477", "no_match", why_not=("收盤價未高於 MA60（below）。",)),
        _Row(
            "2382",
            "unknown",
            why_not=("收盤價與 MA20 的關係未知：暖機資料不足。",),
            conditions=(
                _Condition("close_above_ma20", "unknown", "暖機資料不足", "insufficient_prefix"),
            ),
        ),
    )
    before = deepcopy(snapshot)

    summary = summarize_research_candidates(snapshot, rows, "all")

    assert summary == ResearchCandidateSummary(
        declared_count=4,
        published_count=3,
        missing_count=1,
        match_count=1,
        no_match_count=1,
        unknown_count=2,
        visible_count=3,
        excluded_count=0,
        missing_stock_codes=("2603",),
        excluded_reasons=(),
    )
    assert "2603" not in {row.stock_code for row in rows}
    assert snapshot == before


def test_summary_counts_excluded_published_rows_and_uses_existing_reasons_only() -> None:
    snapshot = _snapshot(("1101", "1477", "2382"), ("1101", "1477", "2382"))
    rows = (
        _Row("1101", "match", why_not=(), conditions=(_Condition("ma20", "match", "已觀察到符合"),)),
        _Row("1477", "no_match", why_not=("收盤價未高於 MA20（below）。",)),
        _Row(
            "2382",
            "unknown",
            why_not=("收盤價與 MA60 的關係未知：來源缺件。",),
            conditions=(_Condition("ma60", "unknown", "來源缺件", "technical_missing"),),
        ),
    )

    summary = summarize_research_candidates(snapshot, rows, "match")

    assert summary.declared_count == 3
    assert summary.published_count == 3
    assert summary.missing_count == 0
    assert summary.match_count == 1
    assert summary.no_match_count == 1
    assert summary.unknown_count == 1
    assert summary.visible_count == 1
    assert summary.excluded_count == 2
    assert summary.excluded_reasons == (
        "1477：整體狀態「不符合」，目前只顯示「符合」。",
        "收盤價未高於 MA20（below）。",
        "2382：整體狀態「未知」，目前只顯示「符合」。",
        "收盤價與 MA60 的關係未知：來源缺件。",
        "technical_missing",
        "來源缺件",
    )


def test_unknown_filter_explains_hidden_match_rows_using_only_filter_state() -> None:
    snapshot = _snapshot(("1101", "1477"), ("1101", "1477"))
    rows = (
        _Row("1101", "match", conditions=(_Condition("ma20", "match"),)),
        _Row("1477", "unknown", why_not=("既有 unknown source reason",)),
    )

    summary = summarize_research_candidates(snapshot, rows, "unknown")

    assert summary.visible_count == 1
    assert summary.excluded_count == 1
    assert summary.excluded_reasons == (
        "1101：整體狀態「符合」，目前只顯示「未知」。",
    )


def test_summary_rejects_bad_denominators_duplicate_and_out_of_scope_rows() -> None:
    with pytest.raises(ValueError, match="宣告股票母體"):
        summarize_research_candidates(
            SimpleNamespace(manifest={}, stock_snapshots={}), (), "all"
        )
    with pytest.raises(ValueError, match="篩選狀態"):
        summarize_research_candidates(_snapshot(("1101",), ("1101",)), (_Row("1101", "match"),), "other")

    snapshot = _snapshot(("1101",), ("1101",))
    with pytest.raises(ValueError, match="重複"):
        summarize_research_candidates(
            snapshot, (_Row("1101", "match"), _Row("1101", "unknown")), "all"
        )
    with pytest.raises(ValueError, match="不屬於已發布 cohort"):
        summarize_research_candidates(snapshot, (_Row("1477", "match"),), "all")
    with pytest.raises(ValueError, match="未宣告股票"):
        summarize_research_candidates(
            _snapshot(("1101",), ("1101", "1477")),
            (_Row("1101", "match"), _Row("1477", "match")),
            "all",
        )


def test_summary_rejects_missing_rows_for_published_artifacts() -> None:
    snapshot = _snapshot(("1101", "1477"), ("1101", "1477"))

    with pytest.raises(ValueError, match="必須完整對應"):
        summarize_research_candidates(snapshot, (_Row("1101", "match"),), "all")
