"""股票名稱搜尋只提供顯示用定位，不賦予名錄或行情任何金融資格。"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import io
from pathlib import Path
import re
from typing import Callable


@dataclass(frozen=True)
class StockSearchEntry:
    code: str
    name: str
    market_label: str


def read_stock_search_directory(
    path: Path, *, cancel_callback: Callable[[], object] | None = None,
) -> tuple[StockSearchEntry, ...]:
    """有界讀取明示名錄；缺件／名稱歧義不補值、不挑選代表代碼。"""
    if not path.is_file():
        return ()
    with path.open("rb") as stream:
        raw = stream.read(4 * 1024 * 1024 + 1)
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError("股票搜尋名錄超過4MiB上限")
    rows = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if not {"stock_id", "stock_name", "type"} <= set(rows.fieldnames or ()):
        raise ValueError("股票搜尋名錄缺少代號、名稱或市場欄位")
    entries: set[StockSearchEntry] = set()
    for index, row in enumerate(rows):
        if cancel_callback is not None and cancel_callback():
            raise ValueError("股票名稱讀取已取消")
        if index >= 20000:
            raise ValueError("股票搜尋名錄超過20000列上限")
        code, name, market = (str(row.get(key) or "").strip() for key in ("stock_id", "stock_name", "type"))
        if re.fullmatch(r"[0-9A-Z]{4,6}", code) and name:
            entries.add(StockSearchEntry(code, name, market))
    return tuple(sorted(entries, key=lambda entry: (entry.code, entry.market_label, entry.name)))
