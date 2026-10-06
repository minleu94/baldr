"""ML-facing compatibility facade for the shared Restated value contract."""

from __future__ import annotations

from dataclasses import asdict
from typing import Sequence

from artifact_contracts.restated_research_contract import (
    OFFICIAL_MARKET_CONTRACT_HASH,
    RESTATED_RESEARCH_PROFILE,
    RestatedResearchInputBinding,
    _hash,
    _require_hash,
    hash_canonical_research_row_payloads,
    require_compatible_market_sources,
)
from ml_module.allocation_contracts import PortfolioMLDatasetRow


def research_rows_hash(rows: Sequence[PortfolioMLDatasetRow]) -> str:
    """綁定實際消費的完整列，包含值、缺值、時鐘與投組狀態。"""
    payloads = [
        asdict(row)
        for row in sorted(rows, key=lambda item: item.symbol)
    ]
    return hash_canonical_research_row_payloads(payloads)
