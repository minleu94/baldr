"""讀取使用者明選的本機題材研究版本，不推定官方用途或歷史可得性。"""
from dataclasses import dataclass, fields
import csv
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from app_module.theme_daily_service import ThemeDailyReport, ThemeDailyService, _aware
from app_module.theme_daily_sqlite_reader import SQLiteThemeMarketReader
from app_module.institutional_daily_snapshot import InstitutionalDailySnapshotPin
from app_module.institutional_source_use import InstitutionalSourceUsePin
from app_module.theme_institutional_reader import TPExThemeFlowReader
from decision_module.industry_theme_map import IndustryThemeMapService, ThemeMappingRow


@dataclass(frozen=True)
class ThemeResearchSnapshot:
    identity_sha256: str
    report: ThemeDailyReport
    mapping: tuple[ThemeMappingRow, ...]


class _MappingReader:
    def __init__(self, rows: list[ThemeMappingRow]):
        self.rows = rows

    def load_pit_mapping(self, as_of_date: str) -> tuple[list[ThemeMappingRow], str, str, str, list[str]]:
        first = self.rows[0]
        return self.rows, first.snapshot_date, first.available_date, "pit_snapshot_aligned", []


_TPEX_FLOW_SCHEMA = "baldr.theme_research_snapshot.tpex_flows.v2"
_TPEX_FLOW_KEYS = frozenset(("schema", "data_date", "saved_completed_at", "mapping", "institutional"))


def _tpex_flow_reader(meta: dict[str, Any], mapping: list[ThemeMappingRow]) -> TPExThemeFlowReader:
    """只將同版映射中精確 tpex 的上櫃股票交給完整TPEx診斷讀者。"""
    record = meta["institutional"]
    keys = {"daily_directory", "manifest_sha256", "receipt_sha256", "source_use_path", "source_use_sha256"}
    if type(record) is not dict or set(record) != keys:
        raise ValueError("TPEx法人版本須明選精確批次與用途五欄")
    if any(type(value) is not str or not value.strip() for value in record.values()):
        raise ValueError("TPEx法人批次與用途欄位須為非空字串")
    for key in ("manifest_sha256", "receipt_sha256", "source_use_sha256"):
        if re.fullmatch(r"[0-9a-f]{64}", record[key], re.ASCII) is None:
            raise ValueError("TPEx法人版本SHA256格式不符")
    directory, policy = Path(record["daily_directory"]), Path(record["source_use_path"])
    if not directory.is_absolute() or not directory.is_dir() or not policy.is_absolute() or not policy.is_file():
        raise ValueError("TPEx法人批次與用途須為既存絕對路徑")
    markets: dict[str, set[str]] = {}
    for row in mapping:
        markets.setdefault(row.stock_id, set()).add(row.market_type)
    if any(len(values) != 1 for values in markets.values()):
        raise ValueError("同一股票的市場分類互相衝突，拒絕法人接線")
    eligible = tuple(sorted(code for code, values in markets.items() if values == {"tpex"}))
    if not eligible:
        raise ValueError("此題材版本沒有可明確識別的上櫃成員")
    return TPExThemeFlowReader(
        InstitutionalDailySnapshotPin(directory, record["manifest_sha256"], record["receipt_sha256"]),
        source_use_pin=InstitutionalSourceUsePin(policy, record["source_use_sha256"]),
        eligible_stock_ids=eligible,
    )

def read_theme_research_snapshot(
    path: Path, *, known_at: datetime | None = None, expected_identity_sha256: str | None = None,
) -> ThemeResearchSnapshot:
    """明選固定版本；v1價格同包，v2外部法人仍核精確pin與原時鐘。"""
    path = path.resolve(strict=True)
    if path.stat().st_size > 32768:
        raise ValueError("題材版本說明超過32KiB")
    raw = path.read_bytes()
    if expected_identity_sha256 is not None and sha256(raw).hexdigest() != expected_identity_sha256:
        raise ValueError("題材版本與原保存身份SHA256不符")
    meta = json.loads(raw)
    if type(meta) is not dict or meta.get("schema") not in ("baldr.theme_research_snapshot.v1", _TPEX_FLOW_SCHEMA):
        raise ValueError("不支援的題材版本格式")
    flow_only = meta["schema"] == _TPEX_FLOW_SCHEMA
    if flow_only:
        if set(meta) != _TPEX_FLOW_KEYS:
            raise ValueError("TPEx法人題材版本不接受價格或其他來源欄位")
        mapping_meta = meta["mapping"]
        if (type(mapping_meta) is not dict or set(mapping_meta) != {"path", "sha256"}
                or type(mapping_meta["path"]) is not str or not mapping_meta["path"].strip()
                or Path(mapping_meta["path"]).is_absolute()
                or type(mapping_meta["sha256"]) is not str
                or re.fullmatch(r"[0-9a-f]{64}", mapping_meta["sha256"], re.ASCII) is None):
            raise ValueError("TPEx法人題材映射須為同包相對路徑與SHA256")
    elif "institutional" in meta:
        raise ValueError("v1題材版本不接受法人接線欄位，請明選v2")
    completed = datetime.fromisoformat(meta["saved_completed_at"])
    _aware(completed)
    completed = completed.astimezone(timezone(timedelta(hours=8)))
    available = completed.replace(minute=0, second=0, microsecond=0)
    if available < completed:
        available += timedelta(hours=1)
    clock = known_at if known_at is not None else datetime.now(timezone.utc)
    _aware(clock)
    if clock < available:
        raise ValueError(f"保存批次尚未到可用小時：{available.isoformat()}")
    files: dict[str, Path] = {}
    file_specs = (("mapping", 4 * 1024 * 1024),) if flow_only else (("mapping", 4 * 1024 * 1024), ("prices", 64 * 1024 * 1024))
    for key, limit in file_specs:
        source = (path.parent / meta[key]["path"]).resolve(strict=True)
        if not source.is_relative_to(path.parent) or not source.is_file() or source.stat().st_size > limit:
            raise ValueError("題材版本的檔案越界或超過大小上限")
        if sha256(source.read_bytes()).hexdigest() != meta[key]["sha256"]:
            raise ValueError("題材版本檔案SHA256不符")
        files[key] = source
    with files["mapping"].open(encoding="utf-8-sig", newline="") as stream:
        csv_reader = csv.DictReader(stream)
        if not {field.name for field in fields(ThemeMappingRow)} <= set(csv_reader.fieldnames or ()):
            raise ValueError("題材對應CSV欄位不完整")
        raw_rows = list(csv_reader)
    if any(not row.get(key, "").strip() for row in raw_rows
           for key in ("chain_name", "theme_name", "stock_id", "snapshot_date", "available_date")):
        raise ValueError("題材對應CSV缺少必要分類或日期")
    mapping = IndustryThemeMapService._read_mapping_csv(files["mapping"])
    if len(mapping) != len(raw_rows):
        raise ValueError("題材對應CSV含無法解析的股票列")
    if not mapping:
        raise ValueError("題材版本沒有股票對應")
    reader = (_tpex_flow_reader(meta, mapping) if flow_only else
              SQLiteThemeMarketReader(files["prices"], expected_sha256=meta["prices"]["sha256"],
                                      available_at=available))
    report = ThemeDailyService(_MappingReader(mapping), reader, mapping_available_at=available).build(
        date.fromisoformat(meta["data_date"]), clock,
    )
    if report.status != "current_research":
        raise ValueError("題材版本日期與成分對應不一致，未載入")
    if sha256(files["mapping"].read_bytes()).hexdigest() != meta["mapping"]["sha256"] or path.read_bytes() != raw:
        raise ValueError("題材版本於讀取期間變動")
    return ThemeResearchSnapshot(sha256(raw).hexdigest(), report, tuple(mapping))
