"""研究時間軸唯讀證據對照的展示契約。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class EvidenceComparisonColumn:
    """單一來源的明示值與限制；未知值不轉換成數值。"""

    title: str
    status: Literal["available", "unavailable", "limited"]
    fields: tuple[tuple[str, str], ...] = ()
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResearchEvidenceComparison:
    """原件與獨立現況讀取並列，不變更原研究或授予金融資格。"""

    original: EvidenceComparisonColumn
    current: EvidenceComparisonColumn
    compared_at: str
