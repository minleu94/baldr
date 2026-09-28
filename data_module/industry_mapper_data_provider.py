"""IndustryMapper 使用的 company／industry frame readers。"""

from __future__ import annotations

import logging
import io
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from data_module.company_registry import (
    COMPANY_REGISTRY_SOURCE_CONTRACT_ATTR,
    load_company_registry_source_contract,
)
from data_module.db_manager import DBManager


logger = logging.getLogger(__name__)
IndustryDatabaseFactory = Callable[[Any], Any]


class IndustryMapperDataProvider:
    """集中讀取產業映射所需的唯讀資料框。"""

    def __init__(
        self,
        config: Any,
        *,
        db_factory: IndustryDatabaseFactory | None = None,
    ) -> None:
        self.config = config
        self._db_factory = db_factory or DBManager

    def load_companies(self) -> pd.DataFrame | None:
        """讀取既有 companies.csv；缺檔或讀取失敗仍回傳 None。"""

        companies_file = self.config.meta_data_dir / "companies.csv"
        if not companies_file.exists():
            print(f"找不到 companies.csv: {companies_file}")
            return None
        try:
            csv_bytes = companies_file.read_bytes()
            frame = pd.read_csv(io.BytesIO(csv_bytes), encoding="utf-8-sig")
            source_contract = load_company_registry_source_contract(
                companies_file,
                csv_bytes=csv_bytes,
            )
            frame.attrs[COMPANY_REGISTRY_SOURCE_CONTRACT_ATTR] = source_contract
            if source_contract["status"] != "captured":
                logger.warning(
                    "companies.csv 來源契約未知，僅供現況分類：%s",
                    source_contract["warnings"],
                )
            logger.info("成功載入 companies.csv，共 %s 筆", len(frame))
            return frame
        except Exception as exc:  # noqa: BLE001 - 保留原相容讀取邊界
            logger.warning("載入 companies.csv 失敗: %s", exc)
            return None

    def load_industry_index_frame(self) -> pd.DataFrame:
        """提供主 application composition 的 SQLite-first / CSV fallback。"""

        if getattr(self.config, "use_sqlite", False):
            try:
                frame = self._db_factory(self.config).execute_query(
                    "SELECT * FROM industry_indices ORDER BY 日期 ASC;"
                )
                if not frame.empty:
                    return frame.copy()
            except Exception as exc:  # noqa: BLE001 - 保留既有降級規則
                logger.warning(
                    "SQLite 載入 industry_indices 失敗，降級 CSV：%s", exc
                )

        for path in self._industry_csv_candidates():
            if path.exists():
                return pd.read_csv(path, encoding="utf-8-sig")
        return pd.DataFrame()

    def load_legacy_industry_index(self) -> pd.DataFrame | None:
        """保留既有非-UI fallback callers 的 None／錯誤降級語意。"""

        if getattr(self.config, "use_sqlite", False):
            try:
                frame = self._db_factory(self.config).execute_query(
                    "SELECT * FROM industry_indices ORDER BY 日期 ASC;"
                )
                if not frame.empty:
                    frame["日期"] = pd.to_datetime(
                        frame["日期"].astype(str),
                        format="%Y%m%d",
                        errors="coerce",
                    )
                    logger.info(
                        "成功從 SQLite 載入 industry_indices，共 %s 筆",
                        len(frame),
                    )
                    return frame
            except Exception as exc:  # noqa: BLE001 - 保留既有 CSV 降級規則
                logger.warning(
                    "從 SQLite 載入 industry_indices 失敗: %s，將降級讀取 CSV",
                    exc,
                )

        industry_file = self.config.industry_index_file
        if not industry_file.exists():
            alternative = self.config.meta_data_dir / "industry_index.csv"
            if alternative.exists():
                industry_file = alternative

        if industry_file.exists():
            try:
                frame = pd.read_csv(industry_file, encoding="utf-8-sig")
                if "日期" in frame.columns:
                    frame["日期"] = pd.to_datetime(
                        frame["日期"],
                        errors="coerce",
                    )
                logger.info("成功載入 industry_index.csv，共 %s 筆", len(frame))
                return frame
            except Exception as exc:  # noqa: BLE001 - 與舊 constructor 一致
                logger.warning("載入 industry_index.csv 失敗: %s", exc)
        else:
            logger.warning("找不到 industry_index.csv: %s", industry_file)
        return None

    def _industry_csv_candidates(self) -> tuple[Path, ...]:
        return (
            self.config.industry_index_file,
            self.config.meta_data_dir / "industry_index.csv",
        )
