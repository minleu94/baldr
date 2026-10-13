"""Portfolio saved Health selection preference with bounded, private atomic storage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any

from app_module.personal_data_paths import to_internal_io_path

SCHEMA = "portfolio-saved-health-selection.v1"
MAX_SELECTION_BYTES = 16 * 1024
_HASH_RE = __import__("re").compile(r"^sha256:[0-9a-f]{64}$")
_FIELDS = frozenset({
    "schema_version", "account_kind", "namespace", "portfolio_id", "snapshot_id",
    "snapshot_rows_sha256", "decision_date", "receipt_id", "receipt_sha256",
    "result_sha256", "status", "selected_position_id", "selected_at",
    "saved_receipt_available_at", "health_observed_at", "source_observed_at",
    "source_available_at", "baseline_saved_available_at",
    "health_source_available_at", "source_witness_status",
})


@dataclass(frozen=True)
class SavedHealthSelection:
    account_kind: str
    namespace: str | None
    portfolio_id: str
    snapshot_id: str
    snapshot_rows_sha256: str
    decision_date: str
    receipt_id: str
    receipt_sha256: str
    result_sha256: str
    status: str
    selected_position_id: str | None
    selected_at: str
    saved_receipt_available_at: str
    health_observed_at: str
    source_observed_at: str
    source_available_at: str | None
    baseline_saved_available_at: str
    health_source_available_at: str | None
    source_witness_status: str

    def __post_init__(self) -> None:
        if self.account_kind != "paper-main" or self.namespace is not None:
            raise ValueError("saved_health_selection_requires_unnamespaced_paper_main")
        if self.portfolio_id != "paper-main" or not self.snapshot_id:
            raise ValueError("saved_health_selection_paper_identity_invalid")
        for name in ("snapshot_rows_sha256", "receipt_sha256", "result_sha256"):
            if not _HASH_RE.fullmatch(str(getattr(self, name) or "")):
                raise ValueError(f"saved_health_selection_{name}_invalid")
        if not self.receipt_id.startswith("phsr-v1-") or len(self.receipt_id) != 72:
            raise ValueError("saved_health_selection_receipt_id_invalid")
        for name in (
            "selected_at",
            "saved_receipt_available_at",
            "health_observed_at",
            "source_observed_at",
            "baseline_saved_available_at",
        ):
            _aware_text(getattr(self, name), name)
        if self.source_available_at is not None:
            _aware_text(self.source_available_at, "source_available_at")
        if self.health_source_available_at is not None and (
            not isinstance(self.health_source_available_at, str)
            or not self.health_source_available_at.strip()
        ):
            raise ValueError("saved_health_selection_health_source_available_at_invalid")
        if self.selected_position_id is not None and not self.selected_position_id.strip():
            raise ValueError("saved_health_selection_position_id_invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA,
            "account_kind": self.account_kind,
            "namespace": self.namespace,
            "portfolio_id": self.portfolio_id,
            "snapshot_id": self.snapshot_id,
            "snapshot_rows_sha256": self.snapshot_rows_sha256,
            "decision_date": self.decision_date,
            "receipt_id": self.receipt_id,
            "receipt_sha256": self.receipt_sha256,
            "result_sha256": self.result_sha256,
            "status": self.status,
            "selected_position_id": self.selected_position_id,
            "selected_at": self.selected_at,
            "saved_receipt_available_at": self.saved_receipt_available_at,
            "health_observed_at": self.health_observed_at,
            "source_observed_at": self.source_observed_at,
            "source_available_at": self.source_available_at,
            "baseline_saved_available_at": self.baseline_saved_available_at,
            "health_source_available_at": self.health_source_available_at,
            "source_witness_status": self.source_witness_status,
        }


class SavedHealthSelectionStore:
    """以輸出根內的單一 preference 保存明確選擇；不保存來源路徑。"""

    def __init__(self, path: str | Path, *, allowed_root: str | Path) -> None:
        self.path = Path(path).expanduser().absolute()
        self.allowed_root = Path(allowed_root).expanduser().absolute()
        try:
            self.path.relative_to(self.allowed_root)
        except ValueError as exc:
            raise ValueError("saved_health_selection_path_outside_output_root") from exc
        if self.path == self.allowed_root:
            raise ValueError("saved_health_selection_path_is_output_root")

    def read(self) -> SavedHealthSelection | None:
        try:
            _verify_parent_chain(self.allowed_root, self.path.parent, create=False)
            raw = _read_stable_bytes(self.path)
        except FileNotFoundError:
            return None
        if len(raw) > MAX_SELECTION_BYTES:
            raise ValueError("saved_health_selection_size_limit")
        value = _strict_object(raw)
        if _canonical_bytes(value) != raw:
            raise ValueError("saved_health_selection_not_canonical")
        if set(value) != _FIELDS or value.get("schema_version") != SCHEMA:
            raise ValueError("saved_health_selection_schema_invalid")
        payload = {name: value[name] for name in _FIELDS if name != "schema_version"}
        record = SavedHealthSelection(**payload)
        return record

    def save(self, record: SavedHealthSelection) -> None:
        if not isinstance(record, SavedHealthSelection):
            raise TypeError("saved_health_selection_record_type_invalid")
        _verify_parent_chain(self.allowed_root, self.path.parent, create=True)
        if _lexists(self.path):
            _require_regular_single_link(os.lstat(to_internal_io_path(self.path)))
        raw = _canonical_bytes(record.to_dict())
        if len(raw) > MAX_SELECTION_BYTES:
            raise ValueError("saved_health_selection_size_limit")
        temporary = self.path.with_name(f".{self.path.name}.{secrets.token_hex(12)}.tmp")
        temporary_io = to_internal_io_path(temporary)
        target_io = to_internal_io_path(self.path)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
        descriptor = os.open(temporary_io, flags, 0o600)
        temp_identity = os.fstat(descriptor)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            _require_regular_single_link(os.lstat(to_internal_io_path(temporary)))
            _verify_parent_chain(self.allowed_root, self.path.parent, create=False)
            if _lexists(self.path):
                _require_regular_single_link(os.lstat(to_internal_io_path(self.path)))
            os.replace(temporary_io, target_io)
            persisted = _read_stable_bytes(self.path)
            if persisted != raw:
                raise ValueError("saved_health_selection_replace_readback_mismatch")
        finally:
            if _lexists(temporary):
                current = os.lstat(to_internal_io_path(temporary))
                if _same_file_identity(current, temp_identity):
                    os.unlink(to_internal_io_path(temporary))
                else:
                    raise ValueError("saved_health_selection_temp_identity_changed")


def new_selection_from_open_result(opened: Any, *, selected_position_id: str | None = None) -> SavedHealthSelection:
    source = opened.source
    health = opened.read_model.health
    if health is None:
        raise ValueError("saved_health_selection_health_projection_missing")
    return SavedHealthSelection(
        account_kind="paper-main",
        namespace=None,
        portfolio_id=opened.snapshot.portfolio_id,
        snapshot_id=opened.snapshot.snapshot_id,
        snapshot_rows_sha256=opened.snapshot.source_snapshot_rows_sha256,
        decision_date=opened.snapshot.decision_date.isoformat(),
        receipt_id=source.receipt_id,
        receipt_sha256=source.receipt_sha256,
        result_sha256=source.result_sha256,
        status=opened.read_model.status,
        selected_position_id=selected_position_id,
        selected_at=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        saved_receipt_available_at=opened.read_model.saved_receipt_available_at or source.available_at,
        health_observed_at=opened.read_model.observed_at or source.observed_at,
        source_observed_at=opened.read_model.source_observed_at or source.source_observed_at,
        source_available_at=opened.read_model.source_available_at,
        baseline_saved_available_at=(
            opened.read_model.baseline_saved_available_at or ""
        ),
        health_source_available_at=opened.read_model.health_source_available_at,
        source_witness_status=opened.read_model.source_witness_status,
    )


def _verify_parent_chain(root: Path, parent: Path, *, create: bool) -> None:
    root = root.absolute()
    parent = parent.absolute()
    try:
        relative = parent.relative_to(root)
    except ValueError as exc:
        raise ValueError("saved_health_selection_parent_outside_root") from exc
    if not _lexists(root):
        if create:
            raise FileNotFoundError("saved_health_selection_allowed_root_missing")
        return
    current = root
    _require_directory(current)
    for part in relative.parts:
        current = current / part
        if not _lexists(current):
            if not create:
                raise FileNotFoundError(str(current))
            os.mkdir(to_internal_io_path(current))
        _require_directory(current)


def _require_directory(path: Path) -> None:
    info = os.lstat(to_internal_io_path(path))
    attributes = int(getattr(info, "st_file_attributes", 0))
    if stat.S_ISLNK(info.st_mode) or attributes & 0x400 or not stat.S_ISDIR(info.st_mode):
        raise ValueError("saved_health_selection_reparse_or_directory_invalid")


def _require_regular_single_link(info: os.stat_result) -> None:
    attributes = int(getattr(info, "st_file_attributes", 0))
    if stat.S_ISLNK(info.st_mode) or attributes & 0x400:
        raise ValueError("saved_health_selection_reparse_rejected")
    if not stat.S_ISREG(info.st_mode) or int(getattr(info, "st_nlink", 1)) != 1:
        raise ValueError("saved_health_selection_regular_single_link_required")
    if info.st_size < 0 or info.st_size > MAX_SELECTION_BYTES:
        raise ValueError("saved_health_selection_size_limit")


def _read_stable_bytes(path: Path) -> bytes:
    before = os.lstat(to_internal_io_path(path))
    _require_regular_single_link(before)
    with open(to_internal_io_path(path), "rb") as stream:
        opened = os.fstat(stream.fileno())
        _require_regular_single_link(opened)
        if not _same_file_identity(before, opened):
            raise ValueError("saved_health_selection_replaced_before_open")
        raw = stream.read(MAX_SELECTION_BYTES + 1)
        after_open = os.fstat(stream.fileno())
    after = os.lstat(to_internal_io_path(path))
    _require_regular_single_link(after_open)
    _require_regular_single_link(after)
    if len(raw) > MAX_SELECTION_BYTES:
        raise ValueError("saved_health_selection_size_limit")
    if not (_same_file_identity(before, after_open) and _same_file_identity(after_open, after)):
        raise ValueError("saved_health_selection_changed_during_read")
    if len(raw) != after.st_size:
        raise ValueError("saved_health_selection_size_changed")
    return raw


def _same_file_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (int(left.st_dev), int(left.st_ino), int(left.st_mode), int(left.st_size), int(left.st_nlink)) == (
        int(right.st_dev), int(right.st_ino), int(right.st_mode), int(right.st_size), int(right.st_nlink)
    )


def _lexists(path: Path) -> bool:
    try:
        os.lstat(to_internal_io_path(path))
    except FileNotFoundError:
        return False
    return True


def _strict_object(raw: bytes) -> dict[str, Any]:
    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("saved_health_selection_duplicate_key")
            result[key] = value
        return result
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs, parse_float=lambda _x: (_ for _ in ()).throw(ValueError("saved_health_selection_float_rejected")))
    if not isinstance(value, dict):
        raise ValueError("saved_health_selection_not_object")
    return value


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _aware_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"saved_health_selection_{field_name}_missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"saved_health_selection_{field_name}_naive")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")
