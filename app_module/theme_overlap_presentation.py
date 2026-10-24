"""同一已載入題材版本內的靜態分類共用股票鄰域。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re

from app_module.theme_daily_service import ThemeDailyReport, ThemeDailyRow
from app_module.theme_research_snapshot import ThemeResearchSnapshot
from decision_module.industry_theme_map import ThemeMappingRow


@dataclass(frozen=True)
class ThemeOverlapNeighbor:
    """單一候選題材及兩側原始分類列，僅表達成員重疊。"""

    chain_name: str
    theme_name: str
    shared_stock_ids: tuple[str, ...]
    shared_stock_names: tuple[str, ...]
    selected_mapping_rows: tuple[ThemeMappingRow, ...]
    neighbor_mapping_rows: tuple[ThemeMappingRow, ...]


@dataclass(frozen=True)
class ThemeOverlapPresentation:
    """同版本、明選題材的有限靜態分類鄰域及版本脈絡。"""

    chain_name: str
    theme_name: str
    selected_member_count: int
    neighbors: tuple[ThemeOverlapNeighbor, ...]
    total_neighbors: int
    omitted_neighbors: int
    snapshot_identity_sha256: str
    data_date: str
    known_at: str
    mapping_snapshot_date: str
    mapping_available_date: str
    historical_pit_eligible: bool


def build_theme_overlap_presentation(
    snapshot: ThemeResearchSnapshot,
    chain_name: str,
    theme_name: str,
) -> ThemeOverlapPresentation:
    """投影明選題材的共用成員；不推導報酬、因果或歷史可得性。"""
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
    if type(report) is not ThemeDailyReport or report.status != "current_research":
        raise ValueError("只接受 current_research 題材版本")
    if type(report.data_date) is not date or type(report.known_at) is not datetime:
        raise TypeError("題材報表資料日或讀取時間型別無效")
    if report.known_at.tzinfo is None or report.known_at.utcoffset() is None:
        raise ValueError("題材報表讀取時間必須包含時區")
    if type(report.historical_pit_eligible) is not bool:
        raise TypeError("historical_pit_eligible 必須是布林值")
    if type(report.rows) is not tuple or type(snapshot.mapping) is not tuple:
        raise TypeError("題材報表 rows 與 mapping 必須是 tuple")

    for value, label in ((report.mapping_snapshot_date, "mapping snapshot"),
                         (report.mapping_available_date, "mapping available")):
        if type(value) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value, re.ASCII) is None:
            raise ValueError(f"{label} 日期格式無效")
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{label} 日期無效") from exc

    report_keys: set[tuple[str, str]] = set()
    report_stocks: dict[tuple[str, str], set[str]] = {}
    for row in report.rows:
        if type(row) is not ThemeDailyRow:
            raise TypeError("題材報表僅接受 ThemeDailyRow")
        if (type(row.chain_name) is not str or not row.chain_name
                or type(row.theme_name) is not str or not row.theme_name
                or type(row.stock_ids) is not tuple
                or any(type(stock_id) is not str or not stock_id for stock_id in row.stock_ids)):
            raise ValueError("題材報表列的鏈、題材或成員格式無效")
        key = (row.chain_name, row.theme_name)
        if key in report_keys:
            raise ValueError("題材報表含重複鏈／題材列")
        report_keys.add(key)
        report_stocks[key] = set(row.stock_ids)

    mappings: dict[tuple[str, str], dict[str, ThemeMappingRow]] = {}
    seen: set[tuple[str, str, str]] = set()
    for mapping_row in snapshot.mapping:
        if type(mapping_row) is not ThemeMappingRow:
            raise TypeError("題材 mapping 僅接受 ThemeMappingRow")
        if (mapping_row.snapshot_date != report.mapping_snapshot_date
                or mapping_row.available_date != report.mapping_available_date):
            raise ValueError("mapping row 日期與報表版本日期不一致")
        key3 = (mapping_row.chain_name, mapping_row.theme_name, mapping_row.stock_id)
        if key3 in seen:
            raise ValueError("題材 mapping 含重複鏈／題材／股票列")
        seen.add(key3)
        mappings.setdefault(key3[:2], {})[mapping_row.stock_id] = mapping_row

    selected_key = (chain_name, theme_name)
    selected_map = mappings.get(selected_key)
    if selected_key not in report_keys or not selected_map:
        raise ValueError("所選產業鏈與題材不存在於此版本的報表及分類")
    selected_ids = set(selected_map) & report_stocks[selected_key]
    if not selected_ids:
        raise ValueError("所選題材沒有可定位的報表成員")

    candidates: list[ThemeOverlapNeighbor] = []
    for key in report_keys:
        if key == selected_key or key not in mappings:
            continue
        candidate_map = mappings[key]
        candidate_ids = set(candidate_map) & report_stocks[key]
        shared_ids = tuple(sorted(selected_ids & candidate_ids))
        if not shared_ids:
            continue
        left_rows = tuple(selected_map[stock_id] for stock_id in shared_ids)
        right_rows = tuple(candidate_map[stock_id] for stock_id in shared_ids)
        candidates.append(ThemeOverlapNeighbor(
            chain_name=key[0], theme_name=key[1],
            shared_stock_ids=shared_ids,
            shared_stock_names=tuple(selected_map[stock_id].stock_name for stock_id in shared_ids),
            selected_mapping_rows=left_rows,
            neighbor_mapping_rows=right_rows,
        ))
    candidates.sort(key=lambda item: (-len(item.shared_stock_ids), item.chain_name, item.theme_name))
    total = len(candidates)
    neighbors = tuple(candidates[:8])
    return ThemeOverlapPresentation(
        chain_name=chain_name, theme_name=theme_name, neighbors=neighbors,
        selected_member_count=len(selected_ids),
        total_neighbors=total, omitted_neighbors=total - len(neighbors),
        snapshot_identity_sha256=snapshot.identity_sha256,
        data_date=report.data_date.isoformat(), known_at=report.known_at.isoformat(),
        mapping_snapshot_date=report.mapping_snapshot_date,
        mapping_available_date=report.mapping_available_date,
        historical_pit_eligible=report.historical_pit_eligible,
    )
