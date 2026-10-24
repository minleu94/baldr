"""題材版本的唯讀分類成員投影；不推導產業方向或市場指標。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re

from app_module.theme_research_snapshot import ThemeResearchSnapshot
from decision_module.industry_theme_map import ThemeMappingRow


@dataclass(frozen=True)
class ThemeClassificationMember:
    """單一 chain/theme/stock 分類列，保留原始來源脈絡。"""

    stock_id: str
    stock_name: str
    market_type: str
    l1_industry_category: str
    chain_tier: str
    is_primary: bool
    assignment_method: str
    source_name: str
    source_tier: str
    pit_mode: str
    evidence_note: str
    snapshot_date: str
    available_date: str


@dataclass(frozen=True)
class ThemeClassificationPresentation:
    """單一明選鏈與題材的分類成員及其版本脈絡。"""

    chain_name: str
    theme_name: str
    members: tuple[ThemeClassificationMember, ...]
    snapshot_identity_sha256: str
    data_date: str
    known_at: str
    mapping_snapshot_date: str
    mapping_available_date: str
    historical_pit_eligible: bool


def build_theme_classification_presentation(
    snapshot: ThemeResearchSnapshot,
    chain_name: str,
    theme_name: str,
) -> ThemeClassificationPresentation:
    """從已讀取版本投影一組分類成員，保留每條 mapping row 的來源資訊。"""
    if type(snapshot) is not ThemeResearchSnapshot:
        raise TypeError("snapshot 必須是 ThemeResearchSnapshot")
    if type(chain_name) is not str or not chain_name.strip():
        raise ValueError("必須明選產業鏈")
    if type(theme_name) is not str or not theme_name.strip():
        raise ValueError("必須明選題材")
    if type(snapshot.identity_sha256) is not str or re.fullmatch(
        r"[0-9a-f]{64}", snapshot.identity_sha256, re.ASCII
    ) is None:
        raise ValueError("題材版本 identity SHA-256 無效")

    report = snapshot.report
    if report.status != "current_research":
        raise ValueError("只接受 current_research 題材版本")
    if type(report.data_date) is not date or type(report.known_at) is not datetime:
        raise TypeError("題材報表資料日或讀取時間型別無效")
    if report.known_at.tzinfo is None or report.known_at.utcoffset() is None:
        raise ValueError("題材報表讀取時間必須包含時區")
    if type(report.historical_pit_eligible) is not bool:
        raise TypeError("historical_pit_eligible 必須是布林值")
    if type(snapshot.mapping) is not tuple:
        raise TypeError("題材 snapshot mapping 必須是 tuple")

    mapping_snapshot_date = report.mapping_snapshot_date
    mapping_available_date = report.mapping_available_date
    selected: list[ThemeMappingRow] = []
    seen: set[tuple[str, str, str]] = set()
    for row in snapshot.mapping:
        if type(row) is not ThemeMappingRow:
            raise TypeError("題材 mapping 僅接受 ThemeMappingRow")
        if (row.snapshot_date != mapping_snapshot_date
                or row.available_date != mapping_available_date):
            raise ValueError("mapping row 日期與報表版本日期不一致")
        if row.chain_name == chain_name and row.theme_name == theme_name:
            key = (row.chain_name, row.theme_name, row.stock_id)
            if key in seen:
                raise ValueError("所選鏈／題材含重複股票分類列")
            seen.add(key)
            selected.append(row)
    if not selected:
        raise ValueError("所選產業鏈與題材不存在於此版本")

    members = tuple(
        ThemeClassificationMember(
            stock_id=row.stock_id,
            stock_name=row.stock_name,
            market_type=row.market_type,
            l1_industry_category=row.l1_industry_category,
            chain_tier=row.chain_tier,
            is_primary=row.is_primary,
            assignment_method=row.assignment_method,
            source_name=row.source_name,
            source_tier=row.source_tier,
            pit_mode=row.pit_mode,
            evidence_note=row.evidence_note,
            snapshot_date=row.snapshot_date,
            available_date=row.available_date,
        )
        for row in sorted(selected, key=lambda item: (item.stock_id, item.stock_name))
    )
    return ThemeClassificationPresentation(
        chain_name=chain_name,
        theme_name=theme_name,
        members=members,
        snapshot_identity_sha256=snapshot.identity_sha256,
        data_date=report.data_date.isoformat(),
        known_at=report.known_at.isoformat(),
        mapping_snapshot_date=mapping_snapshot_date,
        mapping_available_date=mapping_available_date,
        historical_pit_eligible=report.historical_pit_eligible,
    )
