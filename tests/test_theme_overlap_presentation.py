from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from app_module.theme_daily_service import ThemeDailyReport, ThemeDailyRow, ThemeMetricCoverage
from app_module.theme_overlap_presentation import build_theme_overlap_presentation
from app_module.theme_research_snapshot import ThemeResearchSnapshot
from decision_module.industry_theme_map import ThemeMappingRow


def _mapping(stock_id: str, chain: str = "半導體", theme: str = "封裝", **changes: object) -> ThemeMappingRow:
    values: dict[str, object] = {
        "snapshot_date": "2026-10-20", "available_date": "2026-10-21",
        "stock_id": stock_id, "stock_name": f"公司{stock_id}", "market_type": "上市",
        "l1_industry_category": "半導體業", "chain_name": chain, "chain_tier": "中游",
        "theme_name": theme, "is_primary": False, "assignment_method": "rule",
        "source_name": "source-original", "source_tier": "T2", "pit_mode": "quarterly_snapshot",
        "evidence_note": f"evidence-{stock_id}",
    }
    values.update(changes)
    return ThemeMappingRow(**values)  # type: ignore[arg-type]


def _report_row(chain: str, theme: str, *stock_ids: str) -> ThemeDailyRow:
    return ThemeDailyRow(
        chain_name=chain, theme_name=theme, stock_ids=tuple(stock_ids),
        mean_return_pct=None, turnover_twd=None, volume_multiple_5d=None,
        institutional_net_shares=None, institutional_net_turnover_twd=None,
        up_count=0, down_count=0, flat_count=0, institutional_buy_count=0,
        institutional_sell_count=0, institutional_flat_count=0, advancing_ratio=None,
        institutional_buy_ratio=None,
        coverage=ThemeMetricCoverage(len(stock_ids), 0, 0, 0, 0, 0), source_ids=(),
    )


def _snapshot(mapping: tuple[ThemeMappingRow, ...], rows: tuple[ThemeDailyRow, ...], **changes: object) -> ThemeResearchSnapshot:
    values: dict[str, object] = {
        "data_date": date(2026, 10, 21), "known_at": datetime(2026, 10, 21, 9, 30, tzinfo=timezone.utc),
        "mapping_snapshot_date": "2026-10-20", "mapping_available_date": "2026-10-21",
        "status": "current_research", "rows": rows, "warnings": (), "historical_pit_eligible": False,
    }
    values.update(changes)
    return ThemeResearchSnapshot("a" * 64, ThemeDailyReport(**values), mapping)  # type: ignore[arg-type]


def test_overlap_is_version_scoped_ranked_and_retains_both_original_mapping_rows() -> None:
    report_rows = (_report_row("半導體", "封裝", "2330", "2454", "3711"),
                   _report_row("電子", "AI", "2454", "2330"),
                   _report_row("伺服器", "散熱", "3711"),
                   _report_row("無映射", "不可定位", "2330"))
    mapping = (
        _mapping("2330"), _mapping("2454"), _mapping("3711"),
        _mapping("2330", "電子", "AI", source_name="candidate-source", evidence_note="candidate-evidence"),
        _mapping("2454", "電子", "AI", source_name="candidate-source"),
        _mapping("3711", "伺服器", "散熱"),
    )
    result = build_theme_overlap_presentation(_snapshot(mapping, report_rows), "半導體", "封裝")

    assert result.total_neighbors == 2
    assert result.omitted_neighbors == 0
    assert result.selected_member_count == 3
    assert [(item.chain_name, item.theme_name, item.shared_stock_ids) for item in result.neighbors] == [
        ("電子", "AI", ("2330", "2454")), ("伺服器", "散熱", ("3711",)),
    ]
    best = result.neighbors[0]
    assert best.shared_stock_names == ("公司2330", "公司2454")
    assert best.selected_mapping_rows[0].source_name == "source-original"
    assert best.neighbor_mapping_rows[0].source_name == "candidate-source"
    assert best.neighbor_mapping_rows[0].evidence_note == "candidate-evidence"
    assert (result.snapshot_identity_sha256, result.data_date, result.known_at) == (
        "a" * 64, "2026-10-21", "2026-10-21T09:30:00+00:00",
    )
    assert (result.mapping_snapshot_date, result.mapping_available_date, result.historical_pit_eligible) == (
        "2026-10-20", "2026-10-21", False,
    )


def test_neighborhood_caps_at_eight_and_reports_omitted_count_with_stable_ties() -> None:
    names = tuple((f"鏈{i:02}", "題材") for i in range(10))
    mappings = (_mapping("2330"),) + tuple(_mapping("2330", chain, theme) for chain, theme in names)
    rows = (_report_row("半導體", "封裝", "2330"),) + tuple(_report_row(chain, theme, "2330") for chain, theme in names)
    result = build_theme_overlap_presentation(_snapshot(mappings, rows), "半導體", "封裝")

    assert result.total_neighbors == 10
    assert result.omitted_neighbors == 2
    assert len(result.neighbors) == 8
    assert [(item.chain_name, item.theme_name) for item in result.neighbors] == list(names[:8])


def test_absent_selection_and_zero_overlap_are_rejected() -> None:
    mapping = (_mapping("2330"), _mapping("2454", "電子", "AI"))
    rows = (_report_row("半導體", "封裝", "2330"), _report_row("電子", "AI", "2454"))
    snapshot = _snapshot(mapping, rows)
    with pytest.raises(ValueError, match="不存在"):
        build_theme_overlap_presentation(snapshot, "不存在", "不存在")
    result = build_theme_overlap_presentation(snapshot, "半導體", "封裝")
    assert result.neighbors == ()
    assert result.total_neighbors == result.omitted_neighbors == 0


def test_candidate_report_members_without_mapping_are_not_counted_as_overlap() -> None:
    mapping = (
        _mapping("2330"), _mapping("2454"), _mapping("9999"),
        _mapping("2330", "電子", "AI"),
    )
    rows = (
        _report_row("半導體", "封裝", "2330", "2454"),
        # 2454 出現在候選報表，但候選 mapping 沒有此分類列。
        _report_row("電子", "AI", "2330", "2454"),
    )
    result = build_theme_overlap_presentation(_snapshot(mapping, rows), "半導體", "封裝")

    assert result.selected_member_count == 2
    assert len(result.neighbors) == 1
    assert result.neighbors[0].shared_stock_ids == ("2330",)


def test_invalid_identity_unzoned_clock_and_bad_report_date_are_rejected() -> None:
    base = _snapshot((_mapping("2330"),), (_report_row("半導體", "封裝", "2330"),))
    with pytest.raises(ValueError, match="SHA-256"):
        build_theme_overlap_presentation(replace(base, identity_sha256="bad"), "半導體", "封裝")
    with pytest.raises(ValueError, match="時區"):
        build_theme_overlap_presentation(
            replace(base, report=replace(base.report, known_at=datetime(2026, 10, 21, 9, 30))),
            "半導體", "封裝",
        )
    with pytest.raises(ValueError, match="日期無效"):
        build_theme_overlap_presentation(
            replace(base, report=replace(base.report, mapping_available_date="2026-02-30")),
            "半導體", "封裝",
        )


def test_duplicate_mapping_and_mapping_report_date_mismatch_are_rejected() -> None:
    rows = (_report_row("半導體", "封裝", "2330"),)
    with pytest.raises(ValueError, match="重複鏈／題材／股票"):
        build_theme_overlap_presentation(_snapshot((_mapping("2330"), _mapping("2330")), rows), "半導體", "封裝")
    mismatch = replace(_mapping("2330"), available_date="2026-10-22")
    with pytest.raises(ValueError, match="日期與報表版本日期不一致"):
        build_theme_overlap_presentation(_snapshot((mismatch,), rows), "半導體", "封裝")
