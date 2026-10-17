"""重綁具名v4技術來源的新定位鏈；原快照與原收據逐bytes保留。"""
from __future__ import annotations

from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from functools import partial
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from threading import Lock
from typing import Any, Callable, Iterable, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from app_module.daily_market_technical_universe_price_query_v1 import DailyMarketTechnicalUniversePriceReadSessionV1

from app_module.research_output_copy import ResearchOutputCopyBudget
from app_module.daily_market_technical_snapshot_v4_repository import (
    _canonical_directory, _lstat_optional, _read_bounded_file,
)
from app_module.personal_data_paths import to_internal_io_path
from app_module.daily_market_technical_universe_v4_store import (
    DailyMarketTechnicalUniverseV4StoreReader, DailyMarketTechnicalUniverseV4Plan,
    DailyMarketTechnicalUniverseV4Receipt, DailyMarketTechnicalUniverseV4Counts,
    DailyMarketTechnicalUniverseV4ParentReceiptReference,
    _make_receipt as _universe_receipt, _write_immutable,
)
from app_module.rule_research_technical_parent_capture_v4 import (
    DailyMarketTechnicalParentCaptureV4VerifiedRead, DailyMarketTechnicalParentPlanV4,
    DailyMarketTechnicalParentReceiptV4, _make_receipt as _parent_receipt,
)

SCHEMA = "technical-source-copy.v1"
BOOKMARK_COPY_SCHEMA = "technical-price-bookmark-copy.v1"
_HASH = re.compile(r"^[0-9a-f]{64}$")
_ARCHIVE_REUSE_FILE_BYTES = 256 * 1024
_ARCHIVE_REUSE_TOTAL_BYTES = 384 * 1024 * 1024


def _tree_layout(root: Path, maximum: int, cancel=None) -> dict[str, int]:
    """一般plan／receipt／封存目錄清冊；batch內容仍由原strict reader驗。"""
    result: dict[str, int] = {}
    stack = [root]
    count = 0
    while stack:
        directory = _canonical_directory(stack.pop(), must_exist=True)
        with os.scandir(to_internal_io_path(directory)) as iterator:
            entries = sorted(iterator, key=lambda item: item.name)
        for entry in entries:
            _cancel(cancel)
            count += 1
            if count > maximum:
                raise TechnicalSourceCopyError("technical_copy_layout_budget_exceeded")
            path = directory / entry.name
            value = _lstat_optional(path)
            if (value is None or stat.S_ISLNK(value.st_mode)
                    or getattr(value, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
                raise TechnicalSourceCopyError("technical_copy_layout_link_or_revision")
            if stat.S_ISDIR(value.st_mode):
                stack.append(path)
            elif stat.S_ISREG(value.st_mode) and value.st_nlink == 1:
                result[path.relative_to(root).as_posix()] = value.st_size
            else:
                raise TechnicalSourceCopyError("technical_copy_layout_not_regular")
    return result


class TechnicalSourceCopyError(ValueError):
    """新副本未完成；來源不修改，不能採用半成品。"""


@dataclass(frozen=True, slots=True)
class TechnicalSourcePin:
    store_output_root: Path
    generation_identity_sha256: str
    plan_identity_sha256: str
    plan_sha256: str
    receipt_identity_sha256: str
    receipt_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "store_output_root", _canonical_directory(self.store_output_root, must_exist=True))
        if any(type(value) is not str or not _HASH.fullmatch(value) for name, value in self.to_dict().items() if name != "store_output_root"):
            raise TechnicalSourceCopyError("請明選完整具名v4 pins")

    def to_dict(self) -> dict[str, str]:
        return {"store_output_root": str(self.store_output_root),
                "generation_identity_sha256": self.generation_identity_sha256,
                "plan_identity_sha256": self.plan_identity_sha256, "plan_sha256": self.plan_sha256,
                "receipt_identity_sha256": self.receipt_identity_sha256, "receipt_sha256": self.receipt_sha256}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> TechnicalSourcePin:
        if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
            raise TechnicalSourceCopyError("來源pin欄位不完整或多出未支援欄位")
        return cls(**{**value, "store_output_root": Path(value["store_output_root"])})


@dataclass(frozen=True, slots=True)
class _UnverifiedLogicalPin(TechnicalSourcePin):
    """封存原URI只用於closed映射，解碼不構成reader資格。"""
    def __post_init__(self) -> None:
        path = Path(self.store_output_root)
        if not path.is_absolute() or ".." in path.parts:
            raise TechnicalSourceCopyError("technical_copy_logical_root_invalid")
        object.__setattr__(self, "store_output_root", path)
        if any(type(value) is not str or not _HASH.fullmatch(value) for name, value in self.to_dict().items() if name != "store_output_root"):
            raise TechnicalSourceCopyError("technical_copy_logical_pin_invalid")


class _Archive:
    def __init__(self, directory: Path, receipt_sha256: str, budget: ResearchOutputCopyBudget, cancel,
                 *, retain_verified_bytes: bool = False):
        if type(retain_verified_bytes) is not bool:
            raise TechnicalSourceCopyError("technical_copy_archive_reuse_option_invalid")
        self.directory = _canonical_directory(directory, must_exist=True)
        if type(receipt_sha256) is not str or not _HASH.fullmatch(receipt_sha256):
            raise TechnicalSourceCopyError("technical_copy_archive_sha_required")
        self.raw = _read_bounded_file(self.directory / "TECHNICAL_COPY_RECEIPT.json", budget.max_file_bytes)
        if sha256(self.raw).hexdigest() != receipt_sha256:
            raise TechnicalSourceCopyError("technical_copy_archive_sha_mismatch")
        self.sha256 = receipt_sha256
        self.body = json.loads(self.raw)
        if self.body.get("schema") != SCHEMA or self.body.get("status") != "copied_and_strict_readers_verified":
            raise TechnicalSourceCopyError("technical_copy_archive_not_completed")
        raw_pin = self.body["copied_pin"]
        self.pin = _UnverifiedLogicalPin(**{**raw_pin, "store_output_root": Path(raw_pin["store_output_root"])})
        self.logical_root = self.pin.store_output_root.parent.parent
        if self.pin.store_output_root != self.logical_root / "live/universe":
            raise TechnicalSourceCopyError("technical_copy_archive_layout_invalid")
        self.entries: dict[str, tuple[int, str]] = {}
        total = len(self.raw)
        for item in self.body["destination_files"]:
            _cancel(cancel)
            relative = item["path"]
            path = Path(relative)
            if (type(relative) is not str or path.is_absolute() or ".." in path.parts
                    or path.as_posix() != relative or relative in self.entries):
                raise TechnicalSourceCopyError("technical_copy_archive_member_invalid")
            size, digest = item["bytes"], item["sha256"]
            if (type(size) is not int or size < 0 or size > budget.max_file_bytes
                    or type(digest) is not str or not _HASH.fullmatch(digest)):
                raise TechnicalSourceCopyError("technical_copy_archive_member_invalid")
            total += size
            if len(self.entries) + 2 > budget.max_entries or total > budget.max_total_bytes:
                raise TechnicalSourceCopyError("technical_copy_archive_budget_exceeded")
            self.entries[relative] = (size, digest)
        layout = _tree_layout(self.directory, budget.max_entries, cancel)
        if layout != {**{name: size for name, (size, _) in self.entries.items()}, "TECHNICAL_COPY_RECEIPT.json": len(self.raw)}:
            raise TechnicalSourceCopyError("technical_copy_archive_members_changed_or_pending")
        # 只在恢復期間重用初次完整SHA已驗原件；預先串行分配預算，結尾仍重讀全部來源。
        retained_names: set[str] = set()
        remaining = min(_ARCHIVE_REUSE_TOTAL_BYTES, budget.max_total_bytes)
        if retain_verified_bytes:
            for name, (size, _) in self.entries.items():
                if size <= _ARCHIVE_REUSE_FILE_BYTES and size <= remaining:
                    retained_names.add(name)
                    remaining -= size
        self._retained_names = frozenset(retained_names)
        self._verified_bytes: dict[str, bytes] = {}
        self._retain_lock = Lock()
        _run_io((partial(self._verify_member, name, expected, budget.max_file_bytes)
                 for name, expected in self.entries.items()), cancel, workers=4)

    def _verify_member(self, name: str, expected: tuple[int, str], maximum: int) -> None:
        raw = _read_bounded_file(self.directory / name, maximum)
        if (len(raw), sha256(raw).hexdigest()) != expected:
            raise TechnicalSourceCopyError("technical_copy_archive_member_sha_mismatch")
        if name in self._retained_names:
            with self._retain_lock:
                self._verified_bytes[name] = raw

    def retained_bytes(self, logical: Path) -> bytes | None:
        """只回傳closed映射內的已驗不可變bytes；沒有保留的原件照常讀取。"""
        self.resolve(logical)
        return self._verified_bytes.get(logical.relative_to(self.logical_root).as_posix())

    def resolve(self, logical: Path) -> tuple[Path, str | None]:
        if logical == self.logical_root:
            return self.directory, None
        try:
            relative = logical.relative_to(self.logical_root).as_posix()
        except ValueError as error:
            raise TechnicalSourceCopyError("technical_copy_archive_uri_outside_closed_map") from error
        if relative == "TECHNICAL_COPY_RECEIPT.json":
            return self.directory / relative, self.sha256
        if relative in self.entries:
            return self.directory / relative, self.entries[relative][1]
        if any(name.startswith(relative + "/") for name in self.entries):
            return self.directory / relative, None
        raise TechnicalSourceCopyError("technical_copy_archive_uri_not_declared")


def _cancel(callback: Callable[[], bool] | None) -> None:
    if callback is not None and callback():
        raise TechnicalSourceCopyError("technical_copy_cancelled")


def _run_io(work: Iterable[Callable[[], None]], cancel: Callable[[], bool] | None, *, workers: int = 2) -> None:
    """寫入最多兩件、唯讀核對可四件；串行派工與取消，返回前收束全部工作。"""
    if type(workers) is not int or workers not in (2, 4):
        raise TechnicalSourceCopyError("technical_copy_io_workers_invalid")
    pending: deque[Future[None]] = deque()
    iterator = iter(work)
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="technical-copy-io") as executor:
        while True:
            _cancel(cancel)
            if len(pending) == workers:
                pending.popleft().result()
                _cancel(cancel)
            try:
                operation = next(iterator)
            except StopIteration:
                break
            pending.append(executor.submit(operation))
        for future in pending:
            future.result()
    _cancel(cancel)


def _read_state(pin: TechnicalSourcePin, callback=None, cancel=None):
    return DailyMarketTechnicalUniverseV4StoreReader(pin.store_output_root).read_exact_with_verified_parent_callback(
        pin.generation_identity_sha256, pin.plan_identity_sha256, pin.receipt_identity_sha256,
        expected_receipt_sha256=pin.receipt_sha256, expected_plan_sha256=pin.plan_sha256,
        parent_verified_callback=callback, cancel_callback=cancel)


class _Files:
    def __init__(self, budget: ResearchOutputCopyBudget, cancel: Callable[[], bool] | None, archive: _Archive | None = None):
        self.budget = budget
        self.cancel = cancel
        self.source: dict[Path, tuple[int, str]] = {}
        self.destination: dict[Path, tuple[int, str]] = {}
        self.source_bytes = 0
        self.destination_bytes = 0
        self.layouts: dict[Path, dict[str, int]] = {}
        self.archive = archive
        if archive is not None:
            self.source = {archive.logical_root / name: expected for name, expected in archive.entries.items()}
            self.source[archive.logical_root / "TECHNICAL_COPY_RECEIPT.json"] = (len(archive.raw), archive.sha256)
            self.source_bytes = sum(size for size, _ in self.source.values())

    def resolve(self, path: Path) -> tuple[Path, str | None]:
        return self.archive.resolve(path) if self.archive else (path, None)

    def read(self, path: Path, expected: str | None = None) -> bytes:
        _cancel(self.cancel)
        physical, pinned = self.resolve(path)
        raw = self.archive.retained_bytes(path) if self.archive is not None else None
        if raw is None:
            raw = _read_bounded_file(physical, self.budget.max_file_bytes)
        identity = (len(raw), sha256(raw).hexdigest())
        if (expected is not None and identity[1] != expected) or (pinned is not None and identity[1] != pinned):
            raise TechnicalSourceCopyError("technical_copy_source_sha_mismatch")
        if path not in self.source:
            self.source_bytes += len(raw)
            if len(self.source) + 1 > self.budget.max_entries or self.source_bytes > self.budget.max_total_bytes:
                raise TechnicalSourceCopyError("technical_copy_source_budget_exceeded")
            self.source[path] = identity
        elif self.source[path] != identity:
            raise TechnicalSourceCopyError("technical_copy_source_changed")
        return raw

    def _prepare_write(self, path: Path, raw: bytes) -> bool:
        _cancel(self.cancel)
        if path in self.destination:
            if self.destination[path] != (len(raw), sha256(raw).hexdigest()):
                raise TechnicalSourceCopyError("technical_copy_destination_conflict")
            return False
        self.destination_bytes += len(raw)
        if len(self.destination) + 1 > self.budget.max_entries or self.destination_bytes > self.budget.max_total_bytes:
            raise TechnicalSourceCopyError("technical_copy_destination_budget_exceeded")
        self.destination[path] = (len(raw), sha256(raw).hexdigest())
        return True

    def write(self, path: Path, raw: bytes) -> None:
        if self._prepare_write(path, raw):
            _write_immutable(path, raw, maximum=self.budget.max_file_bytes)

    def write_many(self, members: Iterable[tuple[Path, bytes]]) -> None:
        """預算與清冊仍由呼叫端串行登記，最多兩份不可變bytes交給寫入端。"""
        def work() -> Iterable[Callable[[], None]]:
            for path, raw in members:
                if self._prepare_write(path, raw):
                    yield partial(_write_immutable, path, raw, maximum=self.budget.max_file_bytes)
        _run_io(work(), self.cancel)

    def copy_raw(self, paths: dict[Path, Path]) -> None:
        def work() -> Iterable[Callable[[], None]]:
            for source, destination in paths.items():
                raw = self.read(source)
                if self._prepare_write(destination, raw):
                    yield partial(_write_immutable, destination, raw, maximum=self.budget.max_file_bytes)
        _run_io(work(), self.cancel)

    def layout(self, path: Path) -> None:
        physical, _ = self.resolve(path)
        current = _tree_layout(physical, self.budget.max_entries, self.cancel)
        if path in self.layouts and self.layouts[path] != current:
            raise TechnicalSourceCopyError("technical_copy_source_layout_changed")
        self.layouts[path] = current

    def _verify_source(self, path: Path, expected: tuple[int, str]) -> None:
        physical, pinned = self.resolve(path)
        raw = _read_bounded_file(physical, self.budget.max_file_bytes)
        identity = (len(raw), sha256(raw).hexdigest())
        if identity[1] != expected[1] or (pinned is not None and identity[1] != pinned):
            raise TechnicalSourceCopyError("technical_copy_source_sha_mismatch")
        if identity != expected:
            raise TechnicalSourceCopyError("technical_copy_source_changed")

    def _verify_destination(self, path: Path, expected: tuple[int, str]) -> None:
        raw = _read_bounded_file(path, self.budget.max_file_bytes)
        if (len(raw), sha256(raw).hexdigest()) != expected:
            raise TechnicalSourceCopyError("technical_copy_source_or_destination_changed")

    def finish(self) -> None:
        def work() -> Iterable[Callable[[], None]]:
            for path, expected in self.source.items():
                yield partial(self._verify_source, path, expected)
            for path, expected in self.destination.items():
                yield partial(self._verify_destination, path, expected)
        _run_io(work(), self.cancel, workers=4)
        for path, expected_layout in self.layouts.items():
            physical, _ = self.resolve(path)
            if _tree_layout(physical, self.budget.max_entries, self.cancel) != expected_layout:
                raise TechnicalSourceCopyError("technical_copy_source_layout_changed")


def _universe_chain(pin: TechnicalSourcePin, files: _Files) -> tuple[bytes, list[DailyMarketTechnicalUniverseV4Receipt]]:
    directory = pin.store_output_root / "daily_market_technical_universe_v4/generations" / pin.generation_identity_sha256
    files.layout(directory)
    plan = files.read(directory / "plan.json", pin.plan_sha256)
    receipt_id, expected = pin.receipt_identity_sha256, pin.receipt_sha256
    chain: list[DailyMarketTechnicalUniverseV4Receipt] = []
    while True:
        raw = files.read(directory / "receipts" / (receipt_id + ".json"), expected)
        receipt = DailyMarketTechnicalUniverseV4Receipt.from_json(raw)
        if receipt.identity_sha256 != receipt_id or len(chain) >= files.budget.max_entries:
            raise TechnicalSourceCopyError("technical_copy_universe_chain_invalid")
        chain.append(receipt)
        body = receipt.to_dict()
        if body["previous_receipt_identity_sha256"] is None:
            break
        receipt_id, expected = body["previous_receipt_identity_sha256"], body["previous_receipt_sha256"]
    return plan, list(reversed(chain))


def copy_technical_source(pin: TechnicalSourcePin, destination_root: Path, *,
                          budget: ResearchOutputCopyBudget,
                          cancel_callback: Callable[[], bool] | None = None) -> TechnicalSourcePin:
    """複製complete來源並另建定位鏈；不開原DB、不呼叫producer或改指標。"""
    if type(pin) is not TechnicalSourcePin or type(budget) is not ResearchOutputCopyBudget:
        raise TechnicalSourceCopyError("請明選具型別來源及完整複製預算")
    return _copy_technical_source(pin, destination_root, budget=budget, cancel_callback=cancel_callback)


def restore_technical_source(archive_directory: Path, archive_receipt_sha256: str, destination_root: Path, *,
                             budget: ResearchOutputCopyBudget,
                             cancel_callback: Callable[[], bool] | None = None) -> TechnicalSourcePin:
    """封存包可移至新位置；外部SHA＋完整closed files先驗，再由原reader驗新鏈。"""
    if type(budget) is not ResearchOutputCopyBudget:
        raise TechnicalSourceCopyError("請明選具型別複製預算")
    archive = _Archive(archive_directory, archive_receipt_sha256, budget, cancel_callback,
                       retain_verified_bytes=True)
    return _copy_technical_source(archive.pin, destination_root, budget=budget,
        cancel_callback=cancel_callback, archive=archive)


def restore_technical_source_with_price_session(archive_directory: Path, archive_receipt_sha256: str,
        destination_root: Path, *, budget: ResearchOutputCopyBudget,
        cancel_callback: Callable[[], bool] | None = None
        ) -> tuple[TechnicalSourcePin, DailyMarketTechnicalUniversePriceReadSessionV1]:
    """同一strict graph驗證同時收集原F07 session；不重讀或跳過來源守衛。"""
    if type(budget) is not ResearchOutputCopyBudget:
        raise TechnicalSourceCopyError("請明選具型別複製預算")
    archive = _Archive(archive_directory, archive_receipt_sha256, budget, cancel_callback,
                       retain_verified_bytes=True)
    sessions: list[DailyMarketTechnicalUniversePriceReadSessionV1] = []
    pin = _copy_technical_source(archive.pin, destination_root, budget=budget,
        cancel_callback=cancel_callback, archive=archive, price_sessions=sessions)
    if len(sessions) != 1:
        raise TechnicalSourceCopyError("technical_copy_price_session_missing")
    return pin, sessions[0]


def _copy_technical_source(pin: TechnicalSourcePin, destination_root: Path, *,
                           budget: ResearchOutputCopyBudget, cancel_callback=None,
                           archive: _Archive | None = None,
                           price_sessions: list[DailyMarketTechnicalUniversePriceReadSessionV1] | None = None) -> TechnicalSourcePin:
    _cancel(cancel_callback)
    target = _canonical_directory(destination_root, must_exist=False)
    if _lstat_optional(target) is not None:
        raise TechnicalSourceCopyError("technical_copy_destination_exists")
    for text in (os.getenv("DATA_ROOT", "D:/Min/Python/Project/FA_Data"), os.getenv("OUTPUT_ROOT"),
                 os.getenv("PERSONAL_DATA_ROOT"), os.getenv("PERSONAL_STORE_ROOT"), os.getenv("PERSONAL_JOURNAL_ROOT")):
        if text:
            protected = Path(text).absolute()
            if target.is_relative_to(protected) or protected.is_relative_to(target):
                raise TechnicalSourceCopyError("technical_copy_protected_root")
    files = _Files(budget, cancel_callback, archive)
    if archive is not None:
        files.layout(archive.logical_root)
    parents: dict[int, dict[str, Any]] = {}
    repository_roots: dict[Path, Path] = {}
    copied_batches: dict[Path, Path] = {}
    raw_copies: dict[Path, Path] = {}
    source_roots = {pin.store_output_root}

    def collect(index: int, verified: DailyMarketTechnicalParentCaptureV4VerifiedRead) -> None:
        if index in parents or len(parents) >= budget.max_runs:
            raise TechnicalSourceCopyError("technical_copy_parent_budget_or_duplicate")
        parents[index] = {"package": verified.package}
        for batch in verified.verified_batches:
            root = batch.repository_output_root
            source_roots.add(root)
            if root not in repository_roots:
                repository_roots[root] = target / "live/repositories" / f"r{len(repository_roots):06d}"
            manifest = batch.manifest_path
            new_manifest = repository_roots[root] / manifest.relative_to(root)
            copied_batches[manifest] = new_manifest
            files.layout(manifest.parent)
            files.read(manifest, batch.manifest_sha256)
            raw_copies[manifest] = new_manifest
            for ref in batch.artifact_refs:
                path = manifest.parent / ref.relative_path
                files.read(path, ref.sha256)
                raw_copies[path] = repository_roots[root] / path.relative_to(root)

    state = _read_state(pin, collect, cancel_callback) if archive is None else None
    if state is not None and state.receipt.status != "complete":
        raise TechnicalSourceCopyError("technical_copy_complete_source_required")
    plan_raw, universe_chain = _universe_chain(pin, files)
    if universe_chain[-1].status != "complete":
        raise TechnicalSourceCopyError("technical_copy_complete_source_required")
    if state is not None:
        old_references = dict(state.segment_parent_references)
    else:
        old_references = {item.to_dict()["segment_reference"]["segment_index"]:
            DailyMarketTechnicalUniverseV4ParentReceiptReference.from_dict(item.to_dict()["segment_reference"]["parent_reference"])
            for item in universe_chain if item.to_dict()["segment_reference"] is not None}
    if len(old_references) > budget.max_runs:
        raise TechnicalSourceCopyError("technical_copy_parent_budget_exceeded")
    for index, reference in old_references.items():
        root = Path(reference.parent_root)
        source_roots.add(root)
        directory = root / "technical_parents_v4/plans" / reference.parent_plan_identity_sha256
        files.layout(directory)
        raw = files.read(directory / "plan.json", reference.parent_plan_sha256)
        parent_plan = DailyMarketTechnicalParentPlanV4.from_dict(json.loads(raw))
        receipt_id = reference.parent_receipt_identity_sha256
        expected = reference.parent_receipt_sha256
        chain: list[DailyMarketTechnicalParentReceiptV4] = []
        while True:
            body_raw = files.read(directory / "receipts" / (receipt_id + ".json"), expected)
            receipt = DailyMarketTechnicalParentReceiptV4.from_json(body_raw)
            if receipt.identity_sha256 != receipt_id or len(chain) >= budget.max_entries:
                raise TechnicalSourceCopyError("technical_copy_parent_chain_invalid")
            chain.append(receipt)
            previous = receipt.to_dict()["previous_receipt_identity_sha256"]
            if previous is None:
                break
            receipt_id, expected = previous, None
        parents.setdefault(index, {}).update(plan=parent_plan, plan_raw=raw, directory=directory, chain=list(reversed(chain)))
        if archive is not None:
            body = chain[0].to_dict()
            repository = Path(body["repository_output_root"]) if body["repository_output_root"] else None
            if repository is not None and repository not in repository_roots:
                repository_roots[repository] = target / "live/repositories" / f"r{len(repository_roots):06d}"
            for batch in body["batch_artifacts"]:
                if repository is None:
                    raise TechnicalSourceCopyError("technical_copy_archive_repository_missing")
                manifest = Path(batch["manifest_path"])
                files.layout(manifest.parent)
                files.read(manifest, batch["manifest_sha256"])
                destination = repository_roots[repository] / manifest.relative_to(repository)
                copied_batches[manifest] = destination
                raw_copies[manifest] = destination
                for ref in batch["artifact_refs"]:
                    path = manifest.parent / ref["relative_path"]
                    files.read(path, ref["sha256"])
                    raw_copies[path] = repository_roots[repository] / path.relative_to(repository)
    for root in ({archive.directory} if archive else source_roots):
        if target == root or target.is_relative_to(root) or root.is_relative_to(target):
            raise TechnicalSourceCopyError("technical_copy_source_destination_overlap")
    # 一般來源沿原strict reader；封存只先驗closed bytes，仍待新鏈strict reader。
    files.finish()
    target.mkdir(parents=True, exist_ok=False)
    pending = target / ".technical_copy_pending.json"
    _write_immutable(pending, b'{}', maximum=2)
    now = datetime.now(timezone.utc)
    try:
        if archive is not None:
            history = target / "original/history" / archive.sha256
            def history_members() -> Iterable[tuple[Path, bytes]]:
                yield history / "source_copy_receipt.json", files.read(archive.logical_root / "TECHNICAL_COPY_RECEIPT.json", archive.sha256)
                for name in archive.entries:
                    if name.startswith("original/"):
                        yield history / name, files.read(archive.logical_root / name)
            files.write_many(history_members())
        files.copy_raw(raw_copies)
        links: list[dict[str, Any]] = []
        copied_pins: list[TechnicalSourcePin] = []
        def metadata_members() -> Iterable[tuple[Path, bytes]]:
            for index, data in parents.items():
                origin = target / "original/parents" / f"p{index:06d}"
                for name in files.layouts[data["directory"]]:
                    source = data["directory"] / name
                    yield origin / name, files.read(source)
            original_universe = target / "original/universe"
            universe_directory = pin.store_output_root / "daily_market_technical_universe_v4/generations" / pin.generation_identity_sha256
            for name in files.layouts[universe_directory]:
                yield original_universe / name, files.read(universe_directory / name)
            references = {}
            for index, data in sorted(parents.items()):
                root = target / "live/parents" / f"p{index:06d}"
                directory = root / "technical_parents_v4/plans" / data["plan"].identity_sha256
                yield directory / "plan.json", data["plan_raw"]
                previous = None
                for old in data["chain"]:
                    body = old.to_dict()
                    batches = []
                    for item in body["batch_artifacts"]:
                        changed = dict(item)
                        changed["manifest_path"] = str(copied_batches[Path(item["manifest_path"])])
                        batches.append(changed)
                    repository = body["repository_output_root"]
                    new = _parent_receipt(plan=data["plan"], sequence=body["sequence"],
                        previous_receipt_identity_sha256=previous.identity_sha256 if previous else None,
                        status=body["status"], batch_artifacts=batches,
                        repository_output_root=str(repository_roots[Path(repository)]) if repository else None,
                        writer_version=body["writer_version"], error_code=body["error_code"], observed_at=now)
                    yield directory / "receipts" / (new.identity_sha256 + ".json"), new.to_json().encode()
                    previous = new
                assert previous is not None
                references[index] = DailyMarketTechnicalUniverseV4ParentReceiptReference.create(root,
                    parent_plan_identity_sha256=data["plan"].identity_sha256,
                    parent_plan_sha256=sha256(data["plan_raw"]).hexdigest(),
                    parent_receipt_identity_sha256=previous.identity_sha256, parent_receipt_sha256=previous.content_sha256)
                links.append({"segment_index": index, "original": old_references[index].to_dict(), "copied": references[index].to_dict()})
            new_root = target / "live/universe"
            directory = new_root / "daily_market_technical_universe_v4/generations" / pin.generation_identity_sha256
            yield directory / "plan.json", plan_raw
            plan = DailyMarketTechnicalUniverseV4Plan.from_json(plan_raw)
            previous_universe = None
            last = None
            for old in universe_chain:
                body = old.to_dict()
                segment = body["segment_reference"]
                if segment is not None:
                    last = references[segment["segment_index"]]
                new_receipt = _universe_receipt(plan=plan, sequence=body["sequence"], previous=previous_universe,
                    status=body["status"], counts=DailyMarketTechnicalUniverseV4Counts.from_dict(body["counts"]),
                    segment_index=segment["segment_index"] if segment else None,
                    parent_reference=references[segment["segment_index"]] if segment else None,
                    last_parent_reference=last, error_code=body["error_code"])
                yield directory / "receipts" / (new_receipt.identity_sha256 + ".json"), new_receipt.to_json().encode()
                previous_universe = new_receipt
            assert previous_universe is not None
            copied_pin = TechnicalSourcePin(new_root, pin.generation_identity_sha256, pin.plan_identity_sha256,
                pin.plan_sha256, previous_universe.identity_sha256, previous_universe.content_sha256)
            copied_pins.append(copied_pin)
        files.write_many(metadata_members())
        copied_pin = copied_pins[0]
        captured_price_session = None
        if price_sessions is None:
            copied = _read_state(copied_pin, cancel=cancel_callback)
        else:
            from app_module.daily_market_technical_universe_price_query_v1 import open_daily_market_technical_universe_price_read_session_v1
            captured_price_session = open_daily_market_technical_universe_price_read_session_v1(
                **copied_pin.to_dict(), cancel_callback=cancel_callback)
            copied = captured_price_session._state
        if state is not None:
            original = state.plan.to_dict()
            expected_counts = state.counts.to_dict()
            expected_missing = list(state.missing_data_stock_codes)
            expected_calculation = state.calculation_identity_sha256
        else:
            assert archive is not None
            original = DailyMarketTechnicalUniverseV4Plan.from_json(plan_raw).to_dict()
            expected_counts = DailyMarketTechnicalUniverseV4Counts.from_dict(archive.body["counts"]).to_dict()
            expected_missing = archive.body["missing_data_stock_codes"]
            expected_calculation = archive.body["calculation_identity_sha256"]
        if (copied.plan.to_dict() != original or copied.counts.to_dict() != expected_counts
                or list(copied.missing_data_stock_codes) != expected_missing
                or copied.calculation_identity_sha256 != expected_calculation):
            raise TechnicalSourceCopyError("technical_copy_semantic_identity_changed")
        files.finish()
        expected_layout = {path.relative_to(target).as_posix(): size
                           for path, (size, _) in files.destination.items()}
        expected_layout[pending.name] = 2
        if _tree_layout(target, budget.max_entries, cancel_callback) != expected_layout:
            raise TechnicalSourceCopyError("technical_copy_destination_layout_changed")
        payload = {"schema": SCHEMA, "status": "copied_and_strict_readers_verified",
            "created_at_utc": now.isoformat(), "parent_observed_at_basis": "copy_assembly_not_original_production",
            "source_pin": pin.to_dict(), "copied_pin": copied_pin.to_dict(), "parent_links": links,
            "counts": copied.counts.to_dict(), "missing_data_stock_codes": list(copied.missing_data_stock_codes),
            "calculation_identity_sha256": copied.calculation_identity_sha256,
            "restored_from_copy_receipt_sha256": archive.sha256 if archive else None,
            "source_clock_unchanged": True, "source_unchanged": True,
            "snapshot_bytes_reencoded": False, "source_database_opened": False, "full_gate_accepted": False,
            "full_environment_portability_accepted": False,
            "source_files": [{"path": str(path), "bytes": size, "sha256": digest} for path, (size, digest) in files.source.items()],
            "destination_files": [{"path": path.relative_to(target).as_posix(), "bytes": size, "sha256": digest} for path, (size, digest) in files.destination.items()]}
        _write_immutable(target / "TECHNICAL_COPY_RECEIPT.json", json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode(), maximum=budget.max_file_bytes)
        pending.unlink()
        if price_sessions is not None:
            assert captured_price_session is not None
            price_sessions.append(captured_price_session)
        return copied_pin
    except Exception as error:
        _write_immutable(target / "TECHNICAL_COPY_FAILURE.json", json.dumps({"schema": SCHEMA, "reason": str(error)[:2048]}, ensure_ascii=False).encode(), maximum=8192)
        raise


def _bookmark_source_in_copy_chain(archive: _Archive, source: Any, budget: ResearchOutputCopyBudget,
                                   cancel: Callable[[], bool] | None) -> list[str]:
    """只沿封存內已有的外部SHA歷史鏈定位；不碰舊root或搜尋其他副本。"""
    keys = tuple(TechnicalSourcePin.__dataclass_fields__)
    wanted = {key: getattr(source, key) for key in keys}
    body, prefix, digest = archive.body, Path(), archive.sha256
    chain: list[str] = []
    for _ in range(budget.max_runs):
        _cancel(cancel)
        if digest in chain or body.get("schema") != SCHEMA or body.get("status") != "copied_and_strict_readers_verified":
            raise TechnicalSourceCopyError("bookmark_copy_lineage_invalid")
        chain.append(digest)
        if body.get("source_pin") == wanted:
            return chain
        previous = body.get("restored_from_copy_receipt_sha256")
        if type(previous) is not str or not _HASH.fullmatch(previous):
            break
        prefix = prefix / "original/history" / previous
        name = (prefix / "source_copy_receipt.json").as_posix()
        declared = archive.entries.get(name)
        if declared is None or declared[1] != previous:
            raise TechnicalSourceCopyError("bookmark_copy_lineage_not_declared")
        raw = _read_bounded_file(archive.directory / name, budget.max_file_bytes)
        if (len(raw), sha256(raw).hexdigest()) != declared:
            raise TechnicalSourceCopyError("bookmark_copy_lineage_changed")
        prior = json.loads(raw)
        if prior.get("copied_pin") != body.get("source_pin"):
            raise TechnicalSourceCopyError("bookmark_copy_lineage_pin_conflict")
        body, digest = prior, previous
    raise TechnicalSourceCopyError("bookmark_copy_original_source_not_in_lineage")


def copy_price_bookmarks(source_watchlist: Path, source_watchlist_sha256: str,
                         technical_copy_directory: Path, technical_copy_receipt_sha256: str,
                         destination_output_root: Path, *, bookmark_ids: Sequence[str],
                         budget: ResearchOutputCopyBudget,
                         cancel_callback: Callable[[], bool] | None = None,
                         read_session: DailyMarketTechnicalUniversePriceReadSessionV1 | None = None) -> Path:
    """為明選F07收藏建立新清單；原清單逐bytes封存，新ID與完整位置沿革另記。"""
    from app_module.daily_market_technical_universe_price_bookmark_v1 import DailyMarketTechnicalUniversePriceBookmarkV1
    from app_module.daily_market_technical_universe_price_comparison_v1 import DailyMarketTechnicalUniversePriceSelectionV1
    from app_module.daily_market_technical_universe_price_query_v1 import (
        DailyMarketTechnicalUniversePriceQueryV1, DailyMarketTechnicalUniversePriceReadSessionV1,
        open_daily_market_technical_universe_price_read_session_v1,
    )
    from app_module.watchlist_service import WatchlistItem, TECHNICAL_UNIVERSE_PRICE_BOOKMARK_SOURCE, _bookmark_item_name

    if type(budget) is not ResearchOutputCopyBudget:
        raise TechnicalSourceCopyError("bookmark_copy_explicit_budget_required")
    _cancel(cancel_callback)
    if (isinstance(bookmark_ids, (str, bytes)) or not isinstance(bookmark_ids, Sequence)
            or not bookmark_ids or len(bookmark_ids) > budget.max_runs
            or any(type(value) is not str or not _HASH.fullmatch(value) for value in bookmark_ids)
            or len(set(bookmark_ids)) != len(bookmark_ids)):
        raise TechnicalSourceCopyError("bookmark_copy_explicit_ids_required")
    source = _canonical_directory(source_watchlist.parent, must_exist=True) / source_watchlist.name
    stamp = _lstat_optional(source)
    if stamp is None or stamp.st_nlink != 1:
        raise TechnicalSourceCopyError("bookmark_copy_source_not_regular")
    raw = _read_bounded_file(source, budget.max_file_bytes)
    if type(source_watchlist_sha256) is not str or not _HASH.fullmatch(source_watchlist_sha256) or sha256(raw).hexdigest() != source_watchlist_sha256:
        raise TechnicalSourceCopyError("bookmark_copy_source_sha_mismatch")
    source_stamp = (stamp.st_size, stamp.st_mtime_ns, stamp.st_dev, stamp.st_ino, stamp.st_nlink)
    def verify_watchlist_source():
        _canonical_directory(source.parent, must_exist=True)
        current = _lstat_optional(source)
        if (current is None or (current.st_size, current.st_mtime_ns, current.st_dev, current.st_ino, current.st_nlink) != source_stamp
                or _read_bounded_file(source, budget.max_file_bytes) != raw):
            raise TechnicalSourceCopyError("bookmark_copy_source_changed")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise TechnicalSourceCopyError("bookmark_copy_duplicate_json_key")
            result[key] = value
        return result
    def invalid_constant(value):
        raise TechnicalSourceCopyError("bookmark_copy_json_constant_invalid:" + value)
    payload = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)
    if not isinstance(payload, dict) or payload.get("version") != 1 or not isinstance(payload.get("items"), list):
        raise TechnicalSourceCopyError("bookmark_copy_legacy_json_watchlist_required")
    if len(payload["items"]) > budget.max_entries:
        raise TechnicalSourceCopyError("bookmark_copy_entry_budget_exceeded")
    selected: dict[str, tuple[dict[str, Any], DailyMarketTechnicalUniversePriceBookmarkV1]] = {}
    for item in payload["items"]:
        _cancel(cancel_callback)
        if not isinstance(item, dict):
            raise TechnicalSourceCopyError("bookmark_copy_watchlist_item_invalid")
        if item.get("source_id") not in bookmark_ids:
            continue
        original = DailyMarketTechnicalUniversePriceBookmarkV1.from_dict(item.get("research_bookmark"))
        if (item.get("source_id") != original.bookmark_id or item.get("stock_code") != original.stock_code
                or item.get("stock_name") != _bookmark_item_name(original)
                or item.get("source") != TECHNICAL_UNIVERSE_PRICE_BOOKMARK_SOURCE or original.bookmark_id in selected):
            raise TechnicalSourceCopyError("bookmark_copy_watchlist_identity_conflict")
        selected[original.bookmark_id] = (item, original)
    if set(selected) != set(bookmark_ids):
        raise TechnicalSourceCopyError("bookmark_copy_selected_id_missing_or_unsupported")
    target = _canonical_directory(destination_output_root, must_exist=False)
    if _lstat_optional(target) is not None:
        raise TechnicalSourceCopyError("bookmark_copy_destination_exists")
    for text in (os.getenv("DATA_ROOT", "D:/Min/Python/Project/FA_Data"), os.getenv("OUTPUT_ROOT"),
                 os.getenv("PERSONAL_DATA_ROOT"), os.getenv("PERSONAL_STORE_ROOT"), os.getenv("PERSONAL_JOURNAL_ROOT")):
        if text:
            protected = Path(text).absolute()
            if target.is_relative_to(protected) or protected.is_relative_to(target):
                raise TechnicalSourceCopyError("bookmark_copy_protected_root")
    archive = _Archive(technical_copy_directory, technical_copy_receipt_sha256, budget, cancel_callback)
    for root in (source.parent, archive.directory):
        if target.is_relative_to(root) or root.is_relative_to(target):
            raise TechnicalSourceCopyError("bookmark_copy_source_destination_overlap")
    if archive.pin.store_output_root != archive.directory / "live/universe":
        raise TechnicalSourceCopyError("bookmark_copy_restore_source_first")
    if read_session is None:
        session = open_daily_market_technical_universe_price_read_session_v1(
            store_output_root=archive.pin.store_output_root, generation_identity_sha256=archive.pin.generation_identity_sha256,
            plan_identity_sha256=archive.pin.plan_identity_sha256, plan_sha256=archive.pin.plan_sha256,
            receipt_identity_sha256=archive.pin.receipt_identity_sha256, receipt_sha256=archive.pin.receipt_sha256,
            cancel_callback=cancel_callback)
    else:
        if type(read_session) is not DailyMarketTechnicalUniversePriceReadSessionV1:
            raise TechnicalSourceCopyError("bookmark_copy_reader_issued_session_required")
        read_session._validate_issued()
        if {key: getattr(read_session.source, key) for key in TechnicalSourcePin.__dataclass_fields__} != archive.pin.to_dict():
            raise TechnicalSourceCopyError("bookmark_copy_session_pin_mismatch")
        session = read_session
    derived = []
    derived_ids: set[str] = set()
    mapping = []
    queries: dict[str, Any] = {}
    changed_source_fields = {"store_output_root", "receipt_identity_sha256", "receipt_sha256", "p01_read_session_identity_sha256"}
    changed_selection_fields = {"query_json", "page_request_json", "result_identity_sha256", "page_identity_sha256", "source_identity_sha256", "selection_identity_sha256"}
    for identity in bookmark_ids:
        item, original = selected[identity]
        chains = []
        new_selections = []
        for selection in (original.selected, *original.comparison_selections):
            _cancel(cancel_callback)
            old_query = selection.query
            chains.append(_bookmark_source_in_copy_chain(archive, old_query.source, budget, cancel_callback))
            if ({key: value for key, value in old_query.source.to_dict().items() if key not in changed_source_fields}
                    != {key: value for key, value in session.source.to_dict().items() if key not in changed_source_fields}):
                raise TechnicalSourceCopyError("bookmark_copy_source_semantics_changed")
            if old_query.query_identity_sha256 not in queries:
                parameters = {field.name: getattr(old_query, field.name) for field in fields(old_query)
                              if field.name not in {"source", "schema_version", "query_identity_sha256"}}
                new_query = DailyMarketTechnicalUniversePriceQueryV1.create(source=session.source, **parameters)
                result = session.execute(new_query, cancel_callback=cancel_callback)
                queries[old_query.query_identity_sha256] = (new_query, result)
            new_query, result = queries[old_query.query_identity_sha256]
            request = selection.page_request
            new_request = result.create_page_request(request.page_index, page_size=request.page_size)
            page = result.read_page(new_request, cancel_callback=cancel_callback)
            new_selection = DailyMarketTechnicalUniversePriceSelectionV1.from_page(new_query, page, selection.stock_code)
            if ({key: value for key, value in selection.to_dict().items() if key not in changed_selection_fields}
                    != {key: value for key, value in new_selection.to_dict().items() if key not in changed_selection_fields}):
                raise TechnicalSourceCopyError("bookmark_copy_selected_values_or_order_changed")
            new_selections.append(new_selection)
        new_bookmark = DailyMarketTechnicalUniversePriceBookmarkV1.create(
            selected=new_selections[0], scroll_position=original.scroll_position,
            comparison_selections=tuple(new_selections[1:]))
        if new_bookmark.bookmark_id in derived_ids:
            raise TechnicalSourceCopyError("bookmark_copy_derived_identity_collision")
        derived_ids.add(new_bookmark.bookmark_id)
        new_item = dict(item, source_id=new_bookmark.bookmark_id, research_bookmark=new_bookmark.to_dict())
        decoded = WatchlistItem.from_mapping(new_item)
        if decoded.stock_code != new_bookmark.stock_code or decoded.source_id != new_bookmark.bookmark_id:
            raise TechnicalSourceCopyError("bookmark_copy_new_watchlist_identity_invalid")
        derived.append(new_item)
        mapping.append({"original_bookmark_id": original.bookmark_id, "derived_bookmark_id": new_bookmark.bookmark_id,
            "original_bookmark_sha256": sha256(original.to_json().encode()).hexdigest(),
            "derived_bookmark_sha256": sha256(new_bookmark.to_json().encode()).hexdigest(), "copy_receipt_chains": chains})
    _cancel(cancel_callback)
    verify_watchlist_source()
    now = datetime.now(timezone.utc).isoformat()
    new_payload = dict(payload, items=derived, updated_at=now)
    encoded = (json.dumps(new_payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    receipt = {"schema": BOOKMARK_COPY_SCHEMA, "status": "derived_bookmarks_and_source_verified",
        "created_at_utc": now, "source_watchlist_sha256": source_watchlist_sha256,
        "technical_copy_receipt_sha256": technical_copy_receipt_sha256,
        "original_item_count": len(payload["items"]), "selected_item_count": len(derived), "bookmarks": mapping,
        "derived_watchlist_sha256": sha256(encoded).hexdigest(), "original_bytes_preserved": True,
        "unselected_items_in_original_archive_only": True, "configuration_activated": False,
        "source_available_at_unchanged": True, "historical_pit_eligible": False, "full_gate_accepted": False}
    receipt_bytes = json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2).encode()
    if (len(raw) + len(encoded) + len(receipt_bytes) + 2 > budget.max_total_bytes
            or max(len(encoded), len(receipt_bytes)) > budget.max_file_bytes):
        raise TechnicalSourceCopyError("bookmark_copy_byte_budget_exceeded")
    target.mkdir(parents=True, exist_ok=False)
    pending = target / ".bookmark_copy_pending.json"
    _write_immutable(pending, b'{}', maximum=2)
    try:
        _write_immutable(target / "original/source_watchlist.json", raw, maximum=budget.max_file_bytes)
        _write_immutable(target / "watchlist/default.json", encoded, maximum=budget.max_file_bytes)
        if (_read_bounded_file(source, budget.max_file_bytes) != raw
                or _read_bounded_file(target / "watchlist/default.json", budget.max_file_bytes) != encoded):
            raise TechnicalSourceCopyError("bookmark_copy_source_or_destination_changed")
        # 全來源與歷史閉集在成功返回前再核；不沿舊根補讀任何原件。
        _Archive(technical_copy_directory, technical_copy_receipt_sha256, budget, cancel_callback)
        verify_watchlist_source()
        _cancel(cancel_callback)
        path = target / "BOOKMARK_COPY_RECEIPT.json"
        _write_immutable(path, receipt_bytes, maximum=budget.max_file_bytes)
        pending.unlink()
        return path
    except Exception as error:
        _write_immutable(target / "BOOKMARK_COPY_FAILURE.json", json.dumps({"schema": BOOKMARK_COPY_SCHEMA,
            "reason": str(error)[:2048]}, ensure_ascii=False).encode(), maximum=8192)
        raise
