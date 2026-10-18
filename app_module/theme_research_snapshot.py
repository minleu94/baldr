"""讀取使用者明選的本機題材研究版本，不推定官方用途或歷史可得性。"""
from dataclasses import dataclass, fields
import csv
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path

from app_module.theme_daily_service import ThemeDailyReport, ThemeDailyService, _aware
from app_module.theme_daily_sqlite_reader import SQLiteThemeMarketReader
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


def read_theme_research_snapshot(
    path: Path, *, known_at: datetime | None = None, expected_identity_sha256: str | None = None,
) -> ThemeResearchSnapshot:
    """schema固定，檔案同包且SHA相符；成功批次小時前不開啟新版本。"""
    path = path.resolve(strict=True)
    if path.stat().st_size > 32768:
        raise ValueError("題材版本說明超過32KiB")
    raw = path.read_bytes()
    if expected_identity_sha256 is not None and sha256(raw).hexdigest() != expected_identity_sha256:
        raise ValueError("題材版本與原保存身份SHA256不符")
    meta = json.loads(raw)
    if meta.get("schema") != "baldr.theme_research_snapshot.v1":
        raise ValueError("不支援的題材版本格式")
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
    for key, limit in (("mapping", 4 * 1024 * 1024), ("prices", 64 * 1024 * 1024)):
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
    reader = SQLiteThemeMarketReader(files["prices"], expected_sha256=meta["prices"]["sha256"],
                                     available_at=available)
    report = ThemeDailyService(_MappingReader(mapping), reader, mapping_available_at=available).build(
        date.fromisoformat(meta["data_date"]), clock,
    )
    if report.status != "current_research":
        raise ValueError("題材版本日期與成分對應不一致，未載入")
    if sha256(files["mapping"].read_bytes()).hexdigest() != meta["mapping"]["sha256"] or path.read_bytes() != raw:
        raise ValueError("題材版本於讀取期間變動")
    return ThemeResearchSnapshot(sha256(raw).hexdigest(), report, tuple(mapping))
