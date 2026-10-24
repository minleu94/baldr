from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from app_module.theme_classification_presentation import (
    ThemeClassificationMember,
    build_theme_classification_presentation,
)
from app_module.theme_daily_service import ThemeDailyReport
from app_module.theme_research_snapshot import ThemeResearchSnapshot
from decision_module.industry_theme_map import ThemeMappingRow


def _row(
    stock_id: str,
    chain_name: str = "半導體",
    theme_name: str = "先進封裝",
    **overrides: object,
) -> ThemeMappingRow:
    values: dict[str, object] = {
        "snapshot_date": "2026-10-20",
        "available_date": "2026-10-21",
        "stock_id": stock_id,
        "stock_name": f"公司{stock_id}",
        "market_type": "上市",
        "l1_industry_category": "半導體業",
        "chain_name": chain_name,
        "chain_tier": "中游",
        "theme_name": theme_name,
        "is_primary": False,
        "assignment_method": "P3_KEYWORD_EXTRACTION",
        "source_name": "keyword_rule",
        "source_tier": "T2",
        "pit_mode": "quarterly_snapshot",
        "evidence_note": "name_keyword:半導體業",
    }
    values.update(overrides)
    return ThemeMappingRow(**values)  # type: ignore[arg-type]


def _snapshot(
    mapping: tuple[ThemeMappingRow, ...] | None = None,
    *,
    status: str = "current_research",
    identity: str = "a" * 64,
) -> ThemeResearchSnapshot:
    report = ThemeDailyReport(
        data_date=date(2026, 10, 21),
        known_at=datetime(2026, 10, 21, 9, 30, tzinfo=timezone.utc),
        mapping_snapshot_date="2026-10-20",
        mapping_available_date="2026-10-21",
        status=status,
        rows=(),
        warnings=(),
        historical_pit_eligible=False,
    )
    return ThemeResearchSnapshot(
        identity_sha256=identity,
        report=report,
        mapping=mapping if mapping is not None else (_row("2330"),),
    )


def test_selected_classification_preserves_membership_and_version_provenance() -> None:
    snapshot = _snapshot((
        _row("2454", is_primary=True, chain_tier="下游", source_name="curated_ic"),
        _row("2330"),
        _row("2330", chain_name="電子零組件", theme_name="AI伺服器"),
    ))

    result = build_theme_classification_presentation(snapshot, "半導體", "先進封裝")

    assert [member.stock_id for member in result.members] == ["2330", "2454"]
    assert result.members[0] == ThemeClassificationMember(
        stock_id="2330",
        stock_name="公司2330",
        market_type="上市",
        l1_industry_category="半導體業",
        chain_tier="中游",
        is_primary=False,
        assignment_method="P3_KEYWORD_EXTRACTION",
        source_name="keyword_rule",
        source_tier="T2",
        pit_mode="quarterly_snapshot",
        evidence_note="name_keyword:半導體業",
        snapshot_date="2026-10-20",
        available_date="2026-10-21",
    )
    assert result.members[1].is_primary is True
    assert result.members[1].chain_tier == "下游"
    assert result.members[1].source_name == "curated_ic"
    assert result.snapshot_identity_sha256 == "a" * 64
    assert result.data_date == "2026-10-21"
    assert result.known_at == "2026-10-21T09:30:00+00:00"
    assert result.mapping_snapshot_date == "2026-10-20"
    assert result.mapping_available_date == "2026-10-21"
    assert result.historical_pit_eligible is False


def test_missing_optional_source_labels_remain_blank() -> None:
    snapshot = _snapshot((
        _row("2330", assignment_method="", source_name="", source_tier="",
             pit_mode="", evidence_note=""),
    ))

    member = build_theme_classification_presentation(
        snapshot, "半導體", "先進封裝"
    ).members[0]

    assert (member.assignment_method, member.source_name, member.source_tier,
            member.pit_mode, member.evidence_note) == ("", "", "", "", "")


def test_duplicate_selected_membership_is_rejected() -> None:
    with pytest.raises(ValueError, match="重複股票分類列"):
        build_theme_classification_presentation(
            _snapshot((_row("2330"), _row("2330"))), "半導體", "先進封裝"
        )


@pytest.mark.parametrize(
    ("chain_name", "theme_name"),
    [("", "先進封裝"), ("半導體", ""), ("不存在", "不存在")],
)
def test_absent_or_unselected_classification_is_rejected(
    chain_name: str, theme_name: str,
) -> None:
    with pytest.raises(ValueError):
        build_theme_classification_presentation(_snapshot(), chain_name, theme_name)


def test_invalid_snapshot_identity_and_status_are_rejected() -> None:
    with pytest.raises(ValueError, match="identity"):
        build_theme_classification_presentation(
            _snapshot(identity="bad"), "半導體", "先進封裝"
        )
    with pytest.raises(ValueError, match="current_research"):
        build_theme_classification_presentation(
            _snapshot(status="stale"), "半導體", "先進封裝"
        )


def test_mapping_date_mismatch_is_rejected() -> None:
    mismatched = replace(_row("2330"), available_date="2026-10-22")
    with pytest.raises(ValueError, match="版本日期不一致"):
        build_theme_classification_presentation(
            _snapshot((mismatched,)), "半導體", "先進封裝"
        )
