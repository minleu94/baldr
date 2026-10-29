"""月營收 MOPS snapshot 檔案的唯讀選擇與檔名 metadata。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import re
import stat


_SNAPSHOT_FILENAME = re.compile(
    r"^mops_monthly_revenue_snapshot_"
    r"(?P<start>\d{4}-\d{2})_(?P<end>\d{4}-\d{2})_"
    r"(?P<fetch_date>\d{4}-\d{2}-\d{2})\.csv$"
)
_CAPTURE_DIRECTORY = re.compile(r"^run_\d{4}-\d{2}-\d{2}_[0-9a-f]{32}$")


def expected_latest_monthly_revenue_period(reference_date: date) -> str:
    """依每月 10 日申報期限（遇週末順延）回傳預期最新期別。"""

    due_date = date(reference_date.year, reference_date.month, 10)
    if due_date.weekday() == 5:
        due_date += timedelta(days=2)
    elif due_date.weekday() == 6:
        due_date += timedelta(days=1)
    months_back = 1 if reference_date > due_date else 2
    month_index = reference_date.year * 12 + (reference_date.month - 1) - months_back
    year, month_zero = divmod(month_index, 12)
    return f"{year:04d}-{month_zero + 1:02d}"


@dataclass(frozen=True)
class MonthlyRevenueSnapshotInfo:
    """從受控 snapshot 檔名解析出的非正式候選 metadata。"""

    path: Path
    start_period: str | None
    end_period: str | None
    fetch_date: str | None

    @property
    def latest_period(self) -> str | None:
        return self.end_period

    @property
    def is_named_snapshot(self) -> bool:
        return self.end_period is not None and self.fetch_date is not None


def inspect_monthly_revenue_snapshot(path: Path) -> MonthlyRevenueSnapshotInfo:
    """只讀取檔名，不讀取 CSV 內容，也不把檔名當成正式 provenance。"""

    resolved = Path(path).expanduser().resolve()
    match = _SNAPSHOT_FILENAME.match(resolved.name)
    if match is None:
        return MonthlyRevenueSnapshotInfo(
            path=resolved,
            start_period=None,
            end_period=None,
            fetch_date=None,
        )
    return MonthlyRevenueSnapshotInfo(
        path=resolved,
        start_period=match.group("start"),
        end_period=match.group("end"),
        fetch_date=match.group("fetch_date"),
    )


def iter_monthly_revenue_snapshot_files(snapshot_dir: Path) -> tuple[Path, ...]:
    """列出候選 snapshot；忽略備份檔、目錄與 symlink。"""

    root = Path(snapshot_dir).expanduser()
    if _is_reparse_point(root) or not root.is_dir():
        return ()
    candidates = [
        path
        for path in root.glob("mops_monthly_revenue_snapshot_*.csv")
        if _is_safe_snapshot_file(path)
    ]

    captures_root = root / "captures"
    if not _is_reparse_point(captures_root) and captures_root.is_dir():
        for capture_dir in captures_root.iterdir():
            if (
                _CAPTURE_DIRECTORY.fullmatch(capture_dir.name)
                and not _is_reparse_point(capture_dir)
                and capture_dir.is_dir()
            ):
                candidates.extend(
                    path
                    for path in capture_dir.glob("mops_monthly_revenue_snapshot_*.csv")
                    if _is_safe_snapshot_file(path)
                    and _scheduled_capture_is_complete(path)
                )
    return tuple(candidates)


def select_latest_monthly_revenue_snapshot(snapshot_dir: Path) -> Path | None:
    """依資料期別、抓取日選最新 snapshot，而非依檔案大小猜測。"""

    candidates = iter_monthly_revenue_snapshot_files(snapshot_dir)
    if not candidates:
        return None

    def sort_key(path: Path) -> tuple[int, str, str, str, int, str]:
        info = inspect_monthly_revenue_snapshot(path)
        if info.is_named_snapshot:
            return (
                1,
                info.end_period or "",
                info.fetch_date or "",
                info.start_period or "",
                _mtime_ns(path),
                str(path),
            )
        return (0, "", "", "", _mtime_ns(path), str(path))

    return max(candidates, key=sort_key)


def _mtime_ns(path: Path) -> int:
    try:
        return int(path.stat().st_mtime_ns)
    except OSError:
        # 檔案仍可被列出但 metadata 讀取受限時，期別／抓取日排序仍可用。
        return 0


def _is_safe_snapshot_file(path: Path) -> bool:
    return (
        not _is_reparse_point(path)
        and path.is_file()
        and ".before_" not in path.name
    )


def _scheduled_capture_is_complete(path: Path) -> bool:
    """排程候選須有最後發布標記；保留舊手動候選相容性。"""

    capture_dir = path.parent
    marker = capture_dir / "scheduled_capture.json"
    if not marker.exists():
        return True
    complete_path = capture_dir / "capture_complete.json"
    if not _is_safe_snapshot_file(complete_path):
        return False
    try:
        import hashlib
        import json

        payload = json.loads(complete_path.read_text(encoding="utf-8"))
        expected_name = str(payload.get("candidate_file") or "")
        expected_hash = str(payload.get("candidate_sha256") or "")
        expected_receipt_hash = str(payload.get("receipt_sha256") or "")
        receipt_path = capture_dir / "capture_receipt.json"
        if payload.get("status") != "captured" or expected_name != path.name:
            return False
        if not expected_receipt_hash or not _is_safe_snapshot_file(receipt_path):
            return False
        return (
            hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash
            and hashlib.sha256(receipt_path.read_bytes()).hexdigest()
            == expected_receipt_hash
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False


def _is_reparse_point(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & reparse_flag)
