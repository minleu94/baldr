"""單次聚合四個已驗證 source revision namespace。"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Iterable

from data_module import (
    excluded_daily_price_revision,
    formal_market_revision,
    historical_session_revision,
    ml_daily_price_revision_gate,
)
from data_module.contracts.source_revision import (
    SOURCE_REVISION_EVIDENCE_SCHEMA_V1,
    ValidatedSourceEvidenceV1,
    validate_source_evidence_identity_v1,
)


def collect_source_revision_evidence_v1(
    *,
    database_path: Path,
    scope_id: str,
    cutoff_date: date,
    symbols: Iterable[str] | None = None,
    explicit_path: Path | None = None,
) -> ValidatedSourceEvidenceV1:
    """依固定順序收集四個 namespace，全部成功後才發布 aggregate。

    ``scope_id`` 必須由呼叫端提供穩定、非路徑的邏輯識別；本入口不從資料庫
    路徑或即時檔案內容推測。這是一輪獨立的來源檢查，不呼叫 legacy composite
    gate，也不保證多檔、跨 namespace 或跨 SQLite 查詢具原子性。
    """

    validate_source_evidence_identity_v1(
        scope_id=scope_id,
        cutoff_date=cutoff_date,
    )

    namespaces = (
        formal_market_revision.collect_market_revision_evidence(
            database_path,
            cutoff_date,
        ),
        historical_session_revision.collect_session_revision_evidence(
            database_path,
            cutoff_date,
        ),
        excluded_daily_price_revision.collect_excluded_daily_price_revision_evidence(
            database_path,
            cutoff_date,
        ),
        ml_daily_price_revision_gate.collect_daily_price_repair_receipt_evidence(
            database_path=database_path,
            decision_date=cutoff_date,
            symbols=symbols,
            explicit_path=explicit_path,
        ),
    )
    return ValidatedSourceEvidenceV1(
        schema_version=SOURCE_REVISION_EVIDENCE_SCHEMA_V1,
        scope_id=scope_id,
        cutoff_date=cutoff_date,
        namespaces=namespaces,
    )
