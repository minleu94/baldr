"""將具名 owner 對週報的核准追加到唯讀 readiness 投影。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any, Protocol

from app_module.approved_weekly_history_projection import SCHEMA_VERSION


_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_REQUIRED_PROJECTION_KEYS = (
    "review_id",
    "review_hash",
    "period_start",
    "period_end",
    "owner_name",
    "owner_role",
    "approved_at",
    "status",
)
_LEGACY_REQUIRED_PROJECTION_KEYS = tuple(
    key for key in _REQUIRED_PROJECTION_KEYS if key != "owner_name"
)


class WeeklyReviewApprovalHistory(Protocol):
    def get_weekly_review(self, review_id: str) -> Any | None: ...


@dataclass(frozen=True)
class WeeklyReviewApprovalResult:
    saved: bool
    record: dict[str, str] | None = None
    error_code: str = ""
    message: str = ""


class WeeklyReviewApprovalService:
    """寫入 owner 明確核准的週報投影；不授權 formal credit 或 scheduler。"""

    def __init__(
        self,
        history_repository: WeeklyReviewApprovalHistory,
        projection_path: str | Path | None = None,
    ) -> None:
        self._history_repository = history_repository
        self._projection_path = projection_path

    @property
    def projection_configured(self) -> bool:
        return bool(self._projection_path and str(self._projection_path).strip())

    def approve_weekly_review(
        self,
        *,
        projection_path: str | Path | None = None,
        review_id: str,
        review_hash: str,
        period_start: str,
        period_end: str,
        owner_name: str,
        owner_role: str,
        approved_at: str | None = None,
        review_note: str = "",
    ) -> WeeklyReviewApprovalResult:
        """驗證 history pin 後，將單一 period 的 owner 核准以原子方式追加。"""

        values = {
            "review_id": review_id.strip(),
            "review_hash": review_hash.strip().lower(),
            "period_start": period_start.strip(),
            "period_end": period_end.strip(),
            "owner_name": owner_name.strip(),
            "owner_role": owner_role.strip(),
        }
        for key, value in values.items():
            if not value:
                return _failure(f"{key}_required", f"{key} 不可空白。")
        if not _SHA256_PATTERN.fullmatch(values["review_hash"]):
            return _failure("review_hash_invalid", "review_hash 必須是完整 sha256: 雜湊。")
        if values["period_start"] > values["period_end"]:
            return _failure("period_invalid", "period_start 不可晚於 period_end。")

        try:
            record = self._history_repository.get_weekly_review(values["review_id"])
        except Exception as exc:  # noqa: BLE001 - repository failures become UI-safe result codes.
            return _failure("history_lookup_failed", f"無法讀取週報歷史：{exc}")
        if record is None:
            return _failure("history_record_missing", "找不到對應的週報歷史紀錄。")
        if (
            str(record.review_hash) != values["review_hash"]
            or str(record.period_start) != values["period_start"]
            or str(record.period_end) != values["period_end"]
        ):
            return _failure(
                "history_pin_mismatch",
                "週報 hash 或期間已變更；請重新載入最新週報後再覆核。",
            )

        try:
            target = _resolve_projection_target(projection_path or self._projection_path)
            timestamp = approved_at.strip() if approved_at is not None else _utc_now()
            _validate_timestamp(timestamp)
            approval = {
                **values,
                "approved_at": timestamp,
                "status": "approved_weekly_review",
            }
            note = review_note.strip()
            if note:
                approval["review_note"] = note
            _append_projection(target, approval)
        except WeeklyReviewApprovalError as exc:
            return _failure(exc.code, str(exc))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            return _failure("projection_io_error", f"無法讀取或保存核准投影：{exc}")
        return WeeklyReviewApprovalResult(saved=True, record=approval)


def create_weekly_review_approval_service(
    config: Any,
    *,
    projection_path: str | Path | None = None,
) -> WeeklyReviewApprovalService:
    """以唯讀歷史 repository 建立人工投影寫入服務。"""

    from app_module.evidence_operations_history_repository import EvidenceOperationsHistoryRepository

    history = EvidenceOperationsHistoryRepository(config, read_only=True)
    return WeeklyReviewApprovalService(history, projection_path=projection_path)


class WeeklyReviewApprovalError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(code: str, message: str) -> WeeklyReviewApprovalResult:
    return WeeklyReviewApprovalResult(saved=False, error_code=code, message=message)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _validate_timestamp(value: str) -> None:
    if not value.strip():
        raise WeeklyReviewApprovalError("approved_at_required", "approved_at 不可空白。")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WeeklyReviewApprovalError("approved_at_invalid", "approved_at 必須是 ISO 8601 時間。") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise WeeklyReviewApprovalError("approved_at_timezone_required", "approved_at 必須包含時區。")


def _resolve_projection_target(path: str | Path | None) -> Path:
    if path is None or not str(path).strip():
        raise WeeklyReviewApprovalError("projection_path_required", "請先設定 weekly approval projection 路徑。")
    target = Path(path).expanduser().resolve()
    normalized = str(target).replace("\\", "/").lower()
    if "/fa_data/sqlite" in normalized or "/data_root/sqlite" in normalized or "twstock.db" in normalized:
        raise WeeklyReviewApprovalError(
            "formal_database_path_forbidden",
            "核准投影不可放在正式 SQLite 資料庫目錄或 twstock.db 路徑。",
        )
    if target.exists() and not target.is_file():
        raise WeeklyReviewApprovalError("projection_target_not_file", "核准投影目標必須是檔案。")
    if not target.parent.is_dir():
        raise WeeklyReviewApprovalError("projection_parent_missing", "核准投影的父目錄必須已存在。")
    return target


def _append_projection(target: Path, approval: dict[str, str]) -> None:
    lock_path = target.with_name(target.name + ".lock")
    with _projection_lock(lock_path):
        if target.exists():
            payload = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise WeeklyReviewApprovalError("projection_invalid", "核准投影根節點必須是 JSON object。")
            if payload.get("schema_version") != SCHEMA_VERSION:
                raise WeeklyReviewApprovalError("projection_schema_unsupported", "核准投影 schema 不支援。")
            if payload.get("formal_credit_authorized") is not False:
                raise WeeklyReviewApprovalError("formal_credit_flag_forbidden", "核准投影不得授權 formal credit。")
            records = payload.get("records")
            if not isinstance(records, list):
                raise WeeklyReviewApprovalError("projection_records_invalid", "核准投影 records 必須是 JSON array。")
            existing_records = [_validate_existing_record(item) for item in records]
        else:
            existing_records = []

        period = (approval["period_start"], approval["period_end"])
        for existing in existing_records:
            if existing["status"] != "approved_weekly_review":
                continue
            existing_period = (existing["period_start"], existing["period_end"])
            if existing_period == period:
                code = "period_already_approved" if existing["review_hash"] == approval["review_hash"] else "period_hash_already_approved"
                message = (
                    "此週期已核准，投影保持 append-only。"
                    if code == "period_already_approved"
                    else "此週期已核准另一份 hash；不得覆寫舊核准。"
                )
                raise WeeklyReviewApprovalError(code, message)
            if existing["review_id"] == approval["review_id"]:
                raise WeeklyReviewApprovalError("review_already_approved", "此週報紀錄已核准。")

        next_payload = {
            "schema_version": SCHEMA_VERSION,
            "formal_credit_authorized": False,
            "records": [*existing_records, approval],
        }
        _atomic_replace_json(target, next_payload)


def _validate_existing_record(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise WeeklyReviewApprovalError("projection_record_invalid", "核准投影含無效 record。")
    if any(not str(item.get(key, "")).strip() for key in _LEGACY_REQUIRED_PROJECTION_KEYS):
        raise WeeklyReviewApprovalError("projection_record_incomplete", "核准投影 record 缺少必要欄位。")
    return dict(item)


def _atomic_replace_json(target: Path, payload: dict[str, Any]) -> None:
    temp_path = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        with temp_path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


class _projection_lock:
    """跨平台 advisory lock，避免同時追加時遺失其他覆核。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = None

    def __enter__(self):
        self.handle = self.path.open("a+b")
        if os.name == "nt":
            import msvcrt

            self.handle.seek(0)
            if self.handle.read(1) == b"":
                self.handle.seek(0)
                self.handle.write(b"0")
                self.handle.flush()
            self.handle.seek(0)
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
