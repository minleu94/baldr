"""季度財報標準來源 facts；不包含因子 quality 或 mapping policy。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class StatementAvailabilityOverride:
    stock_code: str
    statement_type: str
    period: str
    as_of_date: date
    announced_date: date | None
    available_date: date
    source: str
    source_version: str
    evidence_class: str = ""
    source_hash: str = ""
    revision: int = 0
    parent_revision: int | None = None
    provenance_mode: str = ""


@dataclass(frozen=True, slots=True)
class StatementItemRecord:
    stock_code: str
    statement_type: str
    period: str
    as_of_date: date
    announced_date: date | None
    available_date: date
    item_code: str
    item_name: str
    value: Decimal
    source: str
    source_version: str
    # 舊 SQLite quality 欄位只以 wire literal 保存，領域 adapter 負責解讀。
    legacy_quality_wire_value: str | None = None
    # 研究財報 sidecar 會提供個別／合併範圍；舊表缺欄時沿用合併預設。
    report_basis: str = "consolidated"
    # 保留來源 row code 及其證據；factor adapter 不改動此來源 facts。
    raw_item_code: str | None = None
    item_code_source: str | None = None
    item_code_lineage_sha256: str | None = None
    official_item_name: str | None = None
    xbrl_concept: str | None = None
    candidate_source_version: str | None = None
    industry_category: str | None = None
    semantic_mapping_source: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    period_basis: str | None = None
    value_unit: str | None = None
    value_scale: int | None = None


__all__ = ("StatementAvailabilityOverride", "StatementItemRecord")
