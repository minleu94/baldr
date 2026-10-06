"""IndustryMapper 使用的 company／industry frame readers。"""

from __future__ import annotations

import hashlib
import io
import json
import logging
from datetime import date, datetime, timedelta, timezone
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
_DATE_NOT_PRECOMPUTED = object()

INDUSTRY_INDEX_SOURCE_OBSERVATION_ATTR = "industry_index_source_observation"
INDUSTRY_INDEX_SOURCE_OBSERVATION_SCHEMA_VERSION = "industry-index-source-observation.v1"


def _is_sha256(value: Any) -> bool:
    return (
        type(value) is str
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _industry_index_date_iso(value: Any) -> str | None:
    """依 industry_indices 的 YYYYMMDD／ISO 日期形狀解析日期欄。"""

    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    item = getattr(value, "item", None)
    if callable(item):
        try:
            value = item()
        except (TypeError, ValueError):
            pass
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    if type(value) in (int, float):
        if type(value) is float:
            if not value.is_integer():
                return None
            value = int(value)
        numeric_text = str(value)
        if len(numeric_text) != 8 or not numeric_text.isdigit():
            return None
    text = str(value)
    if (type(value) is int or type(value) is str) and len(text) == 8 and text.isdigit():
        try:
            return datetime.strptime(text, "%Y%m%d").date().isoformat()
        except ValueError:
            return None
    try:
        parsed = pd.to_datetime(value, errors="coerce")
    except (TypeError, ValueError):
        return None
    return None if pd.isna(parsed) else parsed.date().isoformat()


def _industry_index_date_iso_cached(
    value: Any,
    cache: dict[tuple[type[Any], Any], str | None],
) -> str | None:
    """在單次來源觀測內重用重複日期，不跨來源載入保留 cache。"""

    if type(value) not in (str, int, float):
        return _industry_index_date_iso(value)
    if type(value) is float and value != value:
        return _industry_index_date_iso(value)

    cache_key = (type(value), value)
    if cache_key not in cache:
        cache[cache_key] = _industry_index_date_iso(value)
    return cache[cache_key]


def _canonical_frame_value(
    value: Any,
    *,
    column: str,
    parsed_date: Any = _DATE_NOT_PRECOMPUTED,
) -> Any:
    """把載入後的單一儲存格轉成可重算的 JSON scalar。"""

    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass

    if column == "日期":
        parsed_day = (
            _industry_index_date_iso(value)
            if parsed_date is _DATE_NOT_PRECOMPUTED
            else parsed_date
        )
        if parsed_day is not None:
            return parsed_day

    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    item = getattr(value, "item", None)
    if callable(item):
        try:
            value = item()
        except (TypeError, ValueError):
            pass
    if type(value) in (str, int, float, bool):
        if type(value) is float and value in (float("inf"), float("-inf")):
            return {"nonfinite_float": repr(value)}
        return value
    return str(value)


def industry_index_frame_rowset_sha256(frame: pd.DataFrame) -> str:
    """雜湊傳給 mapper 的產業指數列，不代表 upstream source authority。"""

    columns = [str(column) for column in frame.columns]
    # SQLite 查詢的每個交易日會重複出現在多個產業指數列。日期 canonical
    # 結果只依單一儲存格值決定，因此在本次 hash 計算內 memoize，避免對同一
    # YYYYMMDD 重複呼叫 datetime.strptime；cache 不跨 frame／reader 生命週期，
    # 不會把舊來源身份或 freshness 帶到下一次載入。
    date_cache: dict[tuple[type[Any], Any], str | None] = {}

    def canonical_value(value: Any, *, column: str) -> Any:
        if column != "日期":
            return _canonical_frame_value(value, column=column)
        parsed_date = _industry_index_date_iso_cached(value, date_cache)
        return _canonical_frame_value(
            value,
            column=column,
            parsed_date=parsed_date,
        )

    rows = [
        [
            canonical_value(value, column=columns[index])
            for index, value in enumerate(row)
        ]
        for row in frame.itertuples(index=False, name=None)
    ]
    canonical = json.dumps(
        {"columns": columns, "rows": rows},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def industry_index_source_observation_hash_matches(
    observation: Any, *, frame: pd.DataFrame | None = None
) -> bool:
    """驗證 current-only 觀測封套；它不驗證官方可得時間。"""

    if not isinstance(observation, dict):
        return False
    declared = observation.get("observation_sha256")
    if not _is_sha256(declared):
        return False
    storage_kind = observation.get("storage_kind")
    source_id = "sqlite.industry_indices" if storage_kind == "sqlite" else "csv.industry_index"
    if (
        observation.get("schema_version")
        != INDUSTRY_INDEX_SOURCE_OBSERVATION_SCHEMA_VERSION
        or observation.get("scope") != "current_industry_index_rows"
        or observation.get("status") != "unknown"
        or observation.get("pit_eligible") is not False
        or observation.get("available_at") is not None
        or observation.get("published_at") is not None
        or observation.get("time_provenance")
        != "local_observation_only; upstream_capture_receipt_not_recorded"
        or storage_kind not in {"sqlite", "csv"}
        or type(observation.get("row_count")) is not int
        or observation["row_count"] < 0
        or type(observation.get("columns")) is not list
        or any(type(column) is not str for column in observation["columns"])
        or observation.get("source_id") != source_id
        or observation.get("table_name") != ("industry_indices" if storage_kind == "sqlite" else None)
        or (
            observation.get("storage_locator") is not None
            and type(observation.get("storage_locator")) is not str
        )
        or type(observation.get("date_range")) is not dict
        or set(observation["date_range"]) != {"from", "through"}
        or any(
            value is not None and type(value) is not str
            for value in observation["date_range"].values()
        )
        or type(observation.get("warnings")) is not list
        or any(type(warning) is not str for warning in observation["warnings"])
    ):
        return False
    rowset_sha256 = observation.get("rowset_sha256")
    if not _is_sha256(rowset_sha256):
        return False
    body = dict(observation)
    body.pop("observation_sha256", None)
    try:
        observed_at = datetime.fromisoformat(
            str(observation.get("observed_at", "")).replace("Z", "+00:00")
        )
    except ValueError:
        return False
    if observed_at.tzinfo is None or observed_at.utcoffset() != timedelta(0):
        return False
    storage_bytes = observation.get("stored_artifact_bytes")
    storage_hash = observation.get("stored_artifact_sha256")
    if storage_kind == "csv":
        if (
            type(storage_bytes) is not int
            or storage_bytes < 0
            or not _is_sha256(storage_hash)
        ):
            return False
    elif storage_bytes is not None or storage_hash is not None:
        return False
    try:
        canonical = json.dumps(
            body,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        return False
    if declared != "sha256:" + hashlib.sha256(canonical).hexdigest():
        return False
    if frame is None:
        return True
    dates = _industry_index_date_range(frame)
    return (
        observation["row_count"] == len(frame)
        and observation["columns"] == [str(column) for column in frame.columns]
        and observation["date_range"]
        == {"from": dates[0] if dates else None, "through": dates[-1] if dates else None}
        and rowset_sha256 == industry_index_frame_rowset_sha256(frame)
    )


def _industry_index_date_range(frame: pd.DataFrame) -> list[str]:
    if "日期" not in frame.columns:
        return []
    date_cache: dict[tuple[type[Any], Any], str | None] = {}
    return sorted(
        {
            parsed_day
            for value in frame["日期"]
            if (
                parsed_day := _industry_index_date_iso_cached(value, date_cache)
            ) is not None
        }
    )


def _build_industry_index_source_observation(
    frame: pd.DataFrame,
    *,
    storage_kind: str,
    storage_locator: str | None,
    stored_artifact_bytes: bytes | None = None,
) -> dict[str, Any]:
    """封存 mapper 實際載入列的身份，明確不推導來源時間。"""

    dates = _industry_index_date_range(frame)
    source_id = (
        "sqlite.industry_indices"
        if storage_kind == "sqlite"
        else "csv.industry_index"
    )
    observed_at = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )
    observation: dict[str, Any] = {
        "schema_version": INDUSTRY_INDEX_SOURCE_OBSERVATION_SCHEMA_VERSION,
        "scope": "current_industry_index_rows",
        "status": "unknown",
        "pit_eligible": False,
        "source_id": source_id,
        "storage_kind": storage_kind,
        "storage_locator": storage_locator,
        "table_name": "industry_indices" if storage_kind == "sqlite" else None,
        "row_count": int(len(frame)),
        "columns": [str(column) for column in frame.columns],
        "date_range": {
            "from": dates[0] if dates else None,
            "through": dates[-1] if dates else None,
        },
        "rowset_sha256": industry_index_frame_rowset_sha256(frame),
        "available_at": None,
        "published_at": None,
        "observed_at": observed_at,
        "time_provenance": "local_observation_only; upstream_capture_receipt_not_recorded",
        "warnings": ["industry_index_upstream_capture_receipt_not_recorded"],
        "stored_artifact_bytes": (
            len(stored_artifact_bytes) if stored_artifact_bytes is not None else None
        ),
        "stored_artifact_sha256": (
            "sha256:" + hashlib.sha256(stored_artifact_bytes).hexdigest()
            if stored_artifact_bytes is not None
            else None
        ),
    }
    canonical = json.dumps(
        observation,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    observation["observation_sha256"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
    return observation


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
                    return self._attach_industry_index_observation(
                        frame.copy(),
                        storage_kind="sqlite",
                        storage_locator=self._sqlite_locator(),
                    )
            except Exception as exc:  # noqa: BLE001 - 保留既有降級規則
                logger.warning(
                    "SQLite 載入 industry_indices 失敗，降級 CSV：%s", exc
                )

        for path in self._industry_csv_candidates():
            if path.exists():
                csv_bytes = path.read_bytes()
                frame = pd.read_csv(io.BytesIO(csv_bytes), encoding="utf-8-sig")
                return self._attach_industry_index_observation(
                    frame,
                    storage_kind="csv",
                    storage_locator=str(path.resolve()),
                    stored_artifact_bytes=csv_bytes,
                )
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
                    frame = self._attach_industry_index_observation(
                        frame,
                        storage_kind="sqlite",
                        storage_locator=self._sqlite_locator(),
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
                csv_bytes = industry_file.read_bytes()
                frame = pd.read_csv(io.BytesIO(csv_bytes), encoding="utf-8-sig")
                if "日期" in frame.columns:
                    frame["日期"] = pd.to_datetime(
                        frame["日期"],
                        errors="coerce",
                    )
                frame = self._attach_industry_index_observation(
                    frame,
                    storage_kind="csv",
                    storage_locator=str(industry_file.resolve()),
                    stored_artifact_bytes=csv_bytes,
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

    def _sqlite_locator(self) -> str | None:
        database_path = getattr(self.config, "db_file", None)
        if database_path is None:
            return None
        try:
            return str(Path(database_path).resolve())
        except (OSError, TypeError, ValueError):
            return str(database_path)

    @staticmethod
    def _attach_industry_index_observation(
        frame: pd.DataFrame,
        *,
        storage_kind: str,
        storage_locator: str | None,
        stored_artifact_bytes: bytes | None = None,
    ) -> pd.DataFrame:
        observation = _build_industry_index_source_observation(
            frame,
            storage_kind=storage_kind,
            storage_locator=storage_locator,
            stored_artifact_bytes=stored_artifact_bytes,
        )
        frame.attrs[INDUSTRY_INDEX_SOURCE_OBSERVATION_ATTR] = observation
        return frame
