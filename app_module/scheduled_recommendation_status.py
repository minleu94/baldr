"""讀取每日排程推薦狀態中明確綁定的保存結果身份。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping


_MAX_STATUS_BYTES = 1024 * 1024
_RESULT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_TASK_NAME = "baldr-recommendation-snapshot-daily"


@dataclass(frozen=True, slots=True)
class ScheduledRecommendationPointer:
    result_id: str
    decision_date: date
    recommendations_count: int


def _is_reparse_point(value: os.stat_result) -> bool:
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(value, "st_file_attributes", 0)
    return bool(flag and attributes & flag)


def read_latest_scheduled_recommendation_pointer(
    output_root: str | Path,
) -> ScheduledRecommendationPointer:
    """讀取並驗證通過的 snapshot 指標；不做 latest DB 查詢或任何寫入。"""

    root = Path(output_root).expanduser()
    if not root.is_absolute():
        raise ValueError("推薦輸出根目錄必須是絕對路徑")
    try:
        resolved_root = root.resolve(strict=True)
        path = resolved_root / "scheduled" / "recommendation_snapshot" / "latest_status.json"
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or _is_reparse_point(before)
        ):
            raise ValueError("每日推薦狀態必須是一般檔案")
        if before.st_size > _MAX_STATUS_BYTES:
            raise ValueError("每日推薦狀態超過 1 MiB")
        if path.resolve(strict=True).parent != path.parent.resolve(strict=True):
            raise ValueError("每日推薦狀態路徑解析不一致")
        with path.open("rb") as stream:
            raw = stream.read(_MAX_STATUS_BYTES + 1)
        after = path.lstat()
    except (OSError, RuntimeError) as exc:
        raise ValueError("無法安全讀取每日推薦狀態") from exc
    if (
        len(raw) > _MAX_STATUS_BYTES
        or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        or not stat.S_ISREG(after.st_mode)
        or stat.S_ISLNK(after.st_mode)
        or _is_reparse_point(after)
    ):
        raise ValueError("每日推薦狀態在讀取期間改變或不符合檔案限制")
    try:
        payload: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("每日推薦狀態不是有效 UTF-8 JSON") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("每日推薦狀態格式錯誤")
    if (
        payload.get("task") != _TASK_NAME
        or payload.get("status") != "passed"
        or payload.get("confirm") is not False
        or payload.get("writes_recommendation_result") is not True
        or payload.get("writes_evidence_db") is not False
        or payload.get("auto_trading") is not False
        or payload.get("lifecycle_action") is not False
    ):
        raise ValueError("每日推薦狀態未通過唯讀展示所需的安全條件")
    result_id = payload.get("result_id")
    decision_date_raw = payload.get("decision_date")
    count = payload.get("recommendations_count")
    if type(result_id) is not str or _RESULT_ID_PATTERN.fullmatch(result_id) is None:
        raise ValueError("每日推薦狀態缺少安全的精確 result_id")
    if type(decision_date_raw) is not str:
        raise ValueError("每日推薦狀態缺少 decision_date")
    try:
        decision_date = date.fromisoformat(decision_date_raw)
    except ValueError as exc:
        raise ValueError("每日推薦狀態的 decision_date 無效") from exc
    if decision_date.isoformat() != decision_date_raw:
        raise ValueError("每日推薦狀態的 decision_date 必須使用 ISO 格式")
    if type(count) is not int or count < 0:
        raise ValueError("每日推薦狀態的推薦筆數無效")
    payload_root = payload.get("output_root")
    payload_runs = payload.get("runs_dir")
    try:
        if (
            type(payload_root) is not str
            or Path(payload_root).resolve(strict=True) != resolved_root
            or type(payload_runs) is not str
            or Path(payload_runs).resolve(strict=True)
            != (resolved_root / "recommendation" / "runs").resolve(strict=True)
        ):
            raise ValueError("每日推薦狀態與目前保存根目錄不一致")
    except (OSError, RuntimeError) as exc:
        raise ValueError("每日推薦保存根目錄無法核對") from exc
    return ScheduledRecommendationPointer(result_id, decision_date, count)
