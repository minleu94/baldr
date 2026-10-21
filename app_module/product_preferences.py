"""產品導覽偏好；只保存使用者明選的定位，不接受資料或金融資格。"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4


def read_theme_catalog_root(state_root: Path) -> Path | None:
    """唯讀取得先前明選的目錄；不存在時不建立偏好或資料目錄。"""
    path = state_root / "v2_theme_catalog.json"
    if not path.exists():
        return None
    if path.is_symlink() or path.stat().st_size > 4096:
        raise ValueError("題材目錄偏好不是可讀的有限設定檔")
    with path.open("rb") as stream:
        raw = stream.read(4097)
    if len(raw) > 4096:
        raise ValueError("題材目錄偏好超過大小上限")
    value = json.loads(raw)
    if (type(value) is not dict or set(value) != {"schema", "root"}
            or value["schema"] != "baldr.theme_catalog_preference.v1"
            or type(value["root"]) is not str):
        raise ValueError("題材目錄偏好格式不符")
    selected = Path(value["root"])
    if not selected.is_absolute():
        raise ValueError("題材目錄偏好必須是絕對路徑")
    return selected


def save_theme_catalog_root(state_root: Path, selected: Path) -> None:
    """原子保存定位偏好；不複製、修改或產製任何題材快照。"""
    if not selected.is_absolute() or not selected.is_dir():
        raise ValueError("請明選既存的題材版本目錄")
    directory = state_root.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "v2_theme_catalog.json"
    if target.is_symlink():
        raise ValueError("題材目錄偏好不接受符號連結")
    temporary = directory / ("v2_theme_catalog." + uuid4().hex + ".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump({"schema": "baldr.theme_catalog_preference.v1", "root": str(selected.resolve())},
                  stream, ensure_ascii=False)
        stream.write("\n")
    temporary.replace(target)
