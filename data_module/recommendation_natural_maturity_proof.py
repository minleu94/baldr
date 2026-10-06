"""推薦自然成熟的固定二十交易日 proof 薄邊界。

僅委派既有 resolver 重驗原 calendar／TAIEX／exact DB 與評估時序，
不建立來源、不載入 trainer，也不計算成本或 label。ML 舊入口保留相容。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


def verify_natural_maturity_session_proof(
    proof: Mapping[str, Any],
    *,
    capture_date: str,
    label_end_date: str,
    evaluation_at: datetime,
    expected_db_path: str | Path,
) -> Mapping[str, Any]:
    """沿用原二十 session wrapper 的參數、錯誤與嚴格驗證。"""

    if proof.get("horizon_sessions") != 20:
        raise ValueError("natural maturity session horizon must be 20")
    try:
        from data_module.natural_maturity_session_resolver import (
            NaturalMaturitySessionResolver,
        )
    except ImportError as exc:
        raise ValueError("natural maturity session resolver is unavailable") from exc
    return NaturalMaturitySessionResolver.verify_session_proof(
        proof,
        capture_date,
        label_end_date,
        evaluation_at,
        expected_db_path=expected_db_path,
    )
