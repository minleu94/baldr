"""列出已保存的 full-N v4 研究版本 metadata。
每次列頁都會重新 inventory 明示 store tree（最多 100,000 entries），以檢查
cursor 是否過期；時間成本由 store 大小決定，不只由 limit 決定。此 catalog
不開來源 DB、不挑 latest、不核完整 receipt/parent chain。每列都明示為
metadata_unverified；使用者選取後仍須呼叫本模組的 read_exact 或 StoreReader.read_exact。
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
import os
from pathlib import Path
import stat
from typing import Literal, NoReturn, cast

from app_module.daily_market_technical_universe_v4_store import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_PLAN_BYTES,
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_RECEIPT_BYTES,
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_RETAINED_BYTES,
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_STORE_ENTRIES,
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_STORE_DIRECTORY,
    DailyMarketTechnicalUniverseV4Counts,
    DailyMarketTechnicalUniverseV4Plan,
    DailyMarketTechnicalUniverseV4Receipt,
    DailyMarketTechnicalUniverseV4StoreError,
    DailyMarketTechnicalUniverseV4StoreReader,
    DailyMarketTechnicalUniverseV4VerifiedState,
    _canonical_json,
    _is_link_or_reparse,
    _is_sha256,
    _lstat_optional,
    _parse_json,
    _read_canonical_file,
    _sha256_bytes,
)
from app_module.personal_data_paths import to_internal_io_path


DAILY_MARKET_TECHNICAL_UNIVERSE_V4_CATALOG_CURSOR_SCHEMA = (
    "daily-market-technical-universe-v4-catalog-cursor.v1"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_CATALOG_MAX_LIMIT = 100
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_CATALOG_DEFAULT_LIMIT = 20
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_CATALOG_SCAN_NOTICE = (
    "每頁會重新檢查最多 100,000 個 store entries，並讀取最多 64 MiB 的 plan/receipt "
    "bytes 計算 stale-cursor fingerprint；之後依序解析 metadata，直到找到 limit+1 列或掃完。"
    "實際成本由已保存 store 的大小決定，不只由本頁筆數決定。"
)

_TERMINAL_STATUSES = frozenset({"complete", "cancelled", "failed"})
_CURSOR_KEYS = frozenset({
    "schema_version",
    "output_root",
    "inventory_sha256",
    "last_generation_name",
    "last_relative_path",
    "cursor_sha256",
})


class DailyMarketTechnicalUniverseV4CatalogError(ValueError):
    """catalog 查詢的穩定錯誤碼。"""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


def _fail(code: str, message: str | None = None) -> NoReturn:
    raise DailyMarketTechnicalUniverseV4CatalogError(code, message)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseV4CatalogEntry:
    """一筆 metadata 歷史列；它本身不代表完整來源已通過 strict read。"""

    generation_name: str
    relative_path: str
    metadata_state: Literal["metadata_unverified", "diagnostic"]
    source_status: Literal["complete", "cancelled", "failed"] | None
    generation_identity_sha256: str | None
    plan_identity_sha256: str | None
    plan_bytes_sha256: str | None
    receipt_identity_sha256: str | None
    receipt_bytes_sha256: str | None
    source_clock_identity_sha256: str | None
    method_contracts_sha256: str | None
    decision_date: date | None
    universe_id: str | None
    population_version: str | None
    cohort_identity_sha256: str | None
    counts: DailyMarketTechnicalUniverseV4Counts | None
    population_state: Literal["included", "all_excluded", "empty"] | None
    diagnostic_code: str | None

    @property
    def is_selectable(self) -> bool:
        return (
            self.metadata_state == "metadata_unverified"
            and self.source_status in _TERMINAL_STATUSES
            and self.generation_identity_sha256 is not None
            and self.plan_identity_sha256 is not None
            and self.plan_bytes_sha256 is not None
            and self.receipt_identity_sha256 is not None
            and self.receipt_bytes_sha256 is not None
        )


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseV4CatalogPage:
    """有界 catalog 頁與 inventory 完整性資訊。"""

    rows: tuple[DailyMarketTechnicalUniverseV4CatalogEntry, ...]
    next_cursor: str | None
    has_more: bool | None
    scan_complete: bool
    continuation_required: bool
    scanned_entry_count: int
    inventory_sha256: str | None
    source_inventory_state: Literal[
        "no_saved_generations",
        "saved_generations_present",
        "inventory_incomplete",
    ]
    scan_cost_notice: str = DAILY_MARKET_TECHNICAL_UNIVERSE_V4_CATALOG_SCAN_NOTICE


@dataclass(frozen=True, slots=True)
class _InventoryEntry:
    path: Path
    relative_path: str
    kind: Literal["directory", "regular", "invalid"]
    signature: tuple[int, int, int, int, int, int, int, int]
    diagnostic_code: str | None
    content_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class _Inventory:
    entries: tuple[_InventoryEntry, ...]
    inventory_sha256: str | None
    scanned_entry_count: int
    scan_complete: bool
    root_exists: bool
    root_diagnostic: str | None


class DailyMarketTechnicalUniverseV4Catalog:
    """在明示 output root 下列出保存版本 metadata；不執行完整 strict verification。"""

    def __init__(self, output_root: str | Path) -> None:
        try:
            self._reader = DailyMarketTechnicalUniverseV4StoreReader(output_root)
        except (DailyMarketTechnicalUniverseV4StoreError, OSError, ValueError) as exc:
            code = getattr(exc, "code", "technical_universe_v4_catalog_root_invalid")
            raise DailyMarketTechnicalUniverseV4CatalogError(code, str(exc)) from exc
        self.output_root = self._reader.output_root
        self.store_root = self.output_root / DAILY_MARKET_TECHNICAL_UNIVERSE_V4_STORE_DIRECTORY

    def list_page(
        self,
        *,
        limit: int = DAILY_MARKET_TECHNICAL_UNIVERSE_V4_CATALOG_DEFAULT_LIMIT,
        cursor: str | None = None,
    ) -> DailyMarketTechnicalUniverseV4CatalogPage:
        """重掃有界 metadata tree 後回傳一頁；不會將截斷掃描說成全量結果。"""

        if type(limit) is not int or not 1 <= limit <= DAILY_MARKET_TECHNICAL_UNIVERSE_V4_CATALOG_MAX_LIMIT:
            _fail("technical_universe_v4_catalog_limit_invalid")

        inventory = self._scan_inventory()
        last_key: tuple[str, str] | None = None
        inventory_sha = inventory.inventory_sha256
        if cursor is not None:
            last_generation, last_path, cursor_inventory = self._decode_cursor(cursor)
            if not inventory.scan_complete:
                _fail("technical_universe_v4_catalog_inventory_incomplete")
            if inventory_sha is None or cursor_inventory != inventory_sha:
                _fail("technical_universe_v4_catalog_stale_cursor")
            last_key = (last_generation, last_path)
        if not inventory.scan_complete:
            # 不提供 cursor/has_more：未完整 inventory 時不能保證排序頁面沒有漏列。
            rows, _has_more = self._metadata_rows(
                inventory,
                after_key=last_key,
                maximum_rows=limit,
            )
            diagnostic = self._entry(
                generation_name="",
                relative_path="@catalog/inventory",
                diagnostic_code=inventory.root_diagnostic or "catalog_inventory_incomplete",
            )
            merged = tuple(sorted((*rows, diagnostic), key=_entry_key))
            return DailyMarketTechnicalUniverseV4CatalogPage(
                rows=merged[:limit],
                next_cursor=None,
                has_more=None,
                scan_complete=False,
                continuation_required=True,
                scanned_entry_count=inventory.scanned_entry_count,
                inventory_sha256=inventory.inventory_sha256,
                source_inventory_state="inventory_incomplete",
            )

        if inventory_sha is None:
            _fail("technical_universe_v4_catalog_inventory_identity_missing")
        rows, has_more = self._metadata_rows(
            inventory,
            after_key=last_key,
            maximum_rows=limit + 1,
        )
        visible_rows = rows[:limit]
        next_cursor = None
        if has_more and visible_rows:
            last = visible_rows[-1]
            next_cursor = self._encode_cursor(
                inventory_sha,
                last.generation_name,
                last.relative_path,
            )
        return DailyMarketTechnicalUniverseV4CatalogPage(
            rows=visible_rows,
            next_cursor=next_cursor,
            has_more=has_more,
            scan_complete=True,
            continuation_required=False,
            scanned_entry_count=inventory.scanned_entry_count,
            inventory_sha256=inventory_sha,
            source_inventory_state=(
                "saved_generations_present"
                if any(
                    item.relative_path.startswith("generations/")
                    and item.relative_path.count("/") == 1
                    and item.kind == "directory"
                    for item in inventory.entries
                )
                else "no_saved_generations"
            ),
        )

    def read_exact(
        self, entry: DailyMarketTechnicalUniverseV4CatalogEntry
    ) -> DailyMarketTechnicalUniverseV4VerifiedState:
        """選取 metadata 列後走原 StoreReader 完整核 receipt、parent 與所有 pins。"""

        if not isinstance(entry, DailyMarketTechnicalUniverseV4CatalogEntry) or not entry.is_selectable:
            _fail("technical_universe_v4_catalog_entry_not_selectable")
        assert entry.generation_identity_sha256 is not None
        assert entry.plan_identity_sha256 is not None
        assert entry.receipt_identity_sha256 is not None
        assert entry.receipt_bytes_sha256 is not None
        assert entry.plan_bytes_sha256 is not None
        try:
            return self._reader.read_exact(
                entry.generation_identity_sha256,
                entry.plan_identity_sha256,
                entry.receipt_identity_sha256,
                expected_receipt_sha256=entry.receipt_bytes_sha256,
                expected_plan_sha256=entry.plan_bytes_sha256,
            )
        except DailyMarketTechnicalUniverseV4StoreError as exc:
            raise DailyMarketTechnicalUniverseV4CatalogError(exc.code, str(exc)) from exc

    def _scan_inventory(self) -> _Inventory:
        try:
            root_info = _lstat_optional(self.store_root)
        except DailyMarketTechnicalUniverseV4StoreError as exc:
            return _Inventory((), None, 0, False, True, exc.code)
        if root_info is None:
            identity = _inventory_identity(self.output_root, False, ())
            return _Inventory((), identity, 0, True, False, None)
        if not stat.S_ISDIR(root_info.st_mode) or _is_link_or_reparse(root_info):
            identity = _inventory_identity(self.output_root, True, ())
            bad = _InventoryEntry(
                self.store_root,
                "@catalog/store-root",
                "invalid",
                _stat_signature(root_info),
                "catalog_store_root_invalid",
            )
            return _Inventory((bad,), identity, 0, False, True, "catalog_store_root_invalid")

        entries: list[_InventoryEntry] = []
        pending: list[tuple[Path, str]] = [(self.store_root, "")]
        scanned = 0
        total_bytes = 0
        incomplete_code: str | None = None
        stop_for_budget = False
        while pending and not stop_for_budget:
            directory, parent_relative = pending.pop()
            try:
                info = _lstat_optional(directory)
                if info is None or not stat.S_ISDIR(info.st_mode) or _is_link_or_reparse(info):
                    relative = parent_relative or "@catalog/store-root"
                    entries.append(_InventoryEntry(
                        directory,
                        relative,
                        "invalid",
                        _stat_signature(info) if info is not None else (0, 0, 0, 0, 0, 0, 0, 0),
                        "catalog_directory_changed_or_unsafe",
                    ))
                    incomplete_code = "catalog_directory_changed_or_unsafe"
                    continue
                names: list[str] = []
                found_over_budget = False
                with os.scandir(to_internal_io_path(directory)) as scan:
                    for item in scan:
                        if scanned + len(names) >= DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_STORE_ENTRIES:
                            found_over_budget = True
                            break
                        names.append(item.name)
            except OSError:
                relative = parent_relative or "@catalog/store-root"
                entries.append(_InventoryEntry(
                    directory,
                    relative,
                    "invalid",
                    (0, 0, 0, 0, 0, 0, 0, 0),
                    "catalog_directory_scan_failed",
                ))
                incomplete_code = "catalog_directory_scan_failed"
                continue
            names.sort()
            for name in names:
                scanned += 1
                relative = f"{parent_relative}/{name}" if parent_relative else name
                if scanned > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_STORE_ENTRIES:
                    incomplete_code = "catalog_inventory_entry_budget_exceeded"
                    stop_for_budget = True
                    break
                path = directory / name
                try:
                    item_info = _lstat_optional(path)
                except DailyMarketTechnicalUniverseV4StoreError:
                    item_info = None
                if item_info is None:
                    entries.append(_InventoryEntry(
                        path,
                        relative,
                        "invalid",
                        (0, 0, 0, 0, 0, 0, 0, 0),
                        "catalog_entry_missing_or_unavailable",
                    ))
                    incomplete_code = incomplete_code or "catalog_entry_missing_or_unavailable"
                    continue
                signature = _stat_signature(item_info)
                if _is_link_or_reparse(item_info):
                    entries.append(_InventoryEntry(path, relative, "invalid", signature, "catalog_link_or_reparse_rejected"))
                    continue
                if stat.S_ISDIR(item_info.st_mode):
                    entries.append(_InventoryEntry(path, relative, "directory", signature, None))
                    pending.append((path, relative))
                    continue
                if stat.S_ISREG(item_info.st_mode) and item_info.st_nlink == 1:
                    total_bytes += item_info.st_size
                    if total_bytes > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_RETAINED_BYTES:
                        entries.append(_InventoryEntry(path, relative, "invalid", signature, "catalog_inventory_byte_budget_exceeded"))
                        incomplete_code = "catalog_inventory_byte_budget_exceeded"
                        stop_for_budget = True
                        break
                    kind: Literal["regular", "invalid"] = "regular"
                    diagnostic_code: str | None = None
                    content_sha: str | None = None
                    metadata_limit = _metadata_file_limit(relative)
                    if metadata_limit is not None:
                        if item_info.st_size > metadata_limit:
                            kind = "invalid"
                            diagnostic_code = "catalog_metadata_byte_limit"
                        else:
                            try:
                                raw = _read_canonical_file(path, metadata_limit, "catalog_metadata_read_failed")
                                after_read = _lstat_optional(path)
                                if after_read is None or _stat_signature(after_read) != signature or _is_link_or_reparse(after_read):
                                    _fail("catalog_metadata_changed_during_inventory")
                                content_sha = _sha256_bytes(raw)
                            except (DailyMarketTechnicalUniverseV4StoreError, OSError, ValueError) as exc:
                                kind = "invalid"
                                diagnostic_code = getattr(exc, "code", "catalog_metadata_read_failed")
                                incomplete_code = incomplete_code or "catalog_metadata_read_failed"
                    entries.append(_InventoryEntry(path, relative, kind, signature, diagnostic_code, content_sha))
                    continue
                code = "catalog_hardlink_rejected" if stat.S_ISREG(item_info.st_mode) else "catalog_file_type_rejected"
                entries.append(_InventoryEntry(path, relative, "invalid", signature, code))
            if found_over_budget:
                incomplete_code = "catalog_inventory_entry_budget_exceeded"
                stop_for_budget = True
            if stop_for_budget:
                break

        entries.sort(key=lambda entry: entry.relative_path)
        complete = incomplete_code is None
        identity = _inventory_identity(self.output_root, True, entries)
        return _Inventory(tuple(entries), identity, min(scanned, DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_STORE_ENTRIES), complete, True, incomplete_code)

    def _metadata_rows(
        self,
        inventory: _Inventory,
        *,
        after_key: tuple[str, str] | None,
        maximum_rows: int,
    ) -> tuple[tuple[DailyMarketTechnicalUniverseV4CatalogEntry, ...], bool]:
        if not inventory.root_exists:
            return (), False
        by_relative = {entry.relative_path: entry for entry in inventory.entries}
        candidates = self._candidate_keys(inventory)
        if after_key is not None and after_key not in candidates:
            _fail("technical_universe_v4_catalog_cursor_position_missing")
        plan_cache: dict[
            str,
            tuple[DailyMarketTechnicalUniverseV4Plan | None, str | None, str | None],
        ] = {}
        rows: list[DailyMarketTechnicalUniverseV4CatalogEntry] = []
        for generation_name, relative_path in candidates:
            key = (generation_name, relative_path)
            if after_key is not None and key <= after_key:
                continue
            row = self._resolve_candidate(
                generation_name,
                relative_path,
                by_relative,
                plan_cache,
            )
            if row is None:
                continue
            rows.append(row)
            if len(rows) >= maximum_rows:
                # 完整掃描時 maximum_rows 為 limit+1；呼叫端由此判斷 has_more。
                return tuple(rows), True
        return tuple(rows), False

    def _candidate_keys(self, inventory: _Inventory) -> tuple[tuple[str, str], ...]:
        if not inventory.root_exists:
            return ()
        by_relative = {entry.relative_path: entry for entry in inventory.entries}
        candidates: set[tuple[str, str]] = set()
        root_children = {
            entry.relative_path
            for entry in inventory.entries
            if "/" not in entry.relative_path
        }
        if "@catalog/store-root" in by_relative:
            candidates.add(("", "@catalog/store-root"))
        if "generations" not in root_children:
            candidates.add(("", "generations"))
        for root_name in root_children:
            item = by_relative[root_name]
            if root_name == "generations":
                if item.kind != "directory":
                    candidates.add(("", root_name))
            elif root_name == ".writer.lock":
                if item.kind != "regular":
                    candidates.add(("", root_name))
            else:
                candidates.add(("", root_name))

        generation_names = {
            item.relative_path[len("generations/"):].split("/", 1)[0]
            for item in inventory.entries
            if item.relative_path.startswith("generations/")
        }
        for generation_name in generation_names:
            generation_path = f"generations/{generation_name}"
            generation = by_relative.get(generation_path)
            if not _is_sha256(generation_name):
                candidates.add((generation_name, generation_path))
                continue
            if generation is None or generation.kind != "directory":
                candidates.add((generation_name, generation_path))
                continue

            candidates.add((generation_name, f"{generation_path}/plan.json"))
            prefix = generation_path + "/"
            direct_names = {
                item.relative_path[len(prefix):].split("/", 1)[0]
                for item in inventory.entries
                if item.relative_path.startswith(prefix)
            }
            for name in direct_names - {"plan.json", "receipts"}:
                candidates.add((generation_name, f"{generation_path}/{name}"))

            receipts_path = f"{generation_path}/receipts"
            receipts = by_relative.get(receipts_path)
            if receipts is None or receipts.kind != "directory":
                candidates.add((generation_name, receipts_path))
                continue
            receipt_children = [
                item for item in inventory.entries
                if item.relative_path.startswith(receipts_path + "/")
            ]
            if not receipt_children:
                candidates.add((generation_name, receipts_path))
            for item in receipt_children:
                tail = item.relative_path[len(receipts_path) + 1:]
                first_component = tail.split("/", 1)[0]
                if "/" not in tail:
                    candidates.add((generation_name, item.relative_path))
                else:
                    nested_path = f"{receipts_path}/{first_component}"
                    nested = by_relative.get(nested_path)
                    if nested is not None and nested.kind == "directory":
                        candidates.add((generation_name, nested_path))
                    if item.kind == "invalid":
                        candidates.add((generation_name, item.relative_path))

        for item in inventory.entries:
            if item.kind == "invalid" and item.diagnostic_code is not None:
                candidates.add((_generation_for_relative(item.relative_path), item.relative_path))
        return tuple(sorted(candidates))

    def _resolve_candidate(
        self,
        generation_name: str,
        relative_path: str,
        by_relative: Mapping[str, _InventoryEntry],
        plan_cache: dict[
            str,
            tuple[DailyMarketTechnicalUniverseV4Plan | None, str | None, str | None],
        ],
    ) -> DailyMarketTechnicalUniverseV4CatalogEntry | None:
        if relative_path == "generations" or relative_path == "@catalog/store-root" or "/" not in relative_path:
            item = by_relative.get(relative_path)
            fallback = (
                "catalog_generations_root_missing"
                if relative_path == "generations"
                else "catalog_unexpected_store_entry"
            )
            return self._entry(
                "",
                relative_path,
                diagnostic_code=(item.diagnostic_code if item else None) or fallback,
            )

        generation_relative = f"generations/{generation_name}"
        if relative_path == generation_relative:
            item = by_relative.get(relative_path)
            code = (
                "catalog_generation_name_invalid"
                if not _is_sha256(generation_name)
                else "catalog_generation_directory_invalid"
            )
            return self._entry(
                generation_name,
                relative_path,
                diagnostic_code=(item.diagnostic_code if item else None) or code,
            )

        plan_relative = f"{generation_relative}/plan.json"
        if relative_path == plan_relative:
            _plan, _sha, error = self._load_plan(
                generation_name,
                by_relative,
                plan_cache,
            )
            if error is None:
                return None
            return self._entry(generation_name, relative_path, diagnostic_code=error)

        receipts_relative = f"{generation_relative}/receipts"
        if relative_path == receipts_relative:
            item = by_relative.get(relative_path)
            if item is None:
                code = "catalog_receipts_directory_missing"
            elif item.kind != "directory":
                code = item.diagnostic_code or "catalog_receipts_directory_invalid"
            else:
                code = "catalog_receipts_empty"
            return self._entry(generation_name, relative_path, diagnostic_code=code)

        if relative_path.startswith(receipts_relative + "/"):
            remainder = relative_path[len(receipts_relative) + 1:]
            item = by_relative.get(relative_path)
            if "/" in remainder:
                return self._entry(
                    generation_name,
                    relative_path,
                    diagnostic_code=(item.diagnostic_code if item else None)
                    or "catalog_nested_receipts_path_invalid",
                )
            if item is None:
                return self._entry(
                    generation_name,
                    relative_path,
                    diagnostic_code="catalog_receipt_missing",
                )
            if not remainder.endswith(".json") or not _is_sha256(remainder[:-5]):
                return self._entry(
                    generation_name,
                    relative_path,
                    diagnostic_code=item.diagnostic_code or "catalog_receipt_name_invalid",
                )
            if item.kind != "regular":
                return self._entry(
                    generation_name,
                    relative_path,
                    diagnostic_code=item.diagnostic_code or "catalog_receipt_file_invalid",
                )
            try:
                raw = _read_canonical_file(
                    item.path,
                    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_RECEIPT_BYTES,
                    "catalog_receipt_read_failed",
                )
                self._verify_scanned_signature(item)
                receipt_sha = _sha256_bytes(raw)
                if item.content_sha256 != receipt_sha:
                    _fail("catalog_metadata_bytes_changed_during_scan")
                receipt = DailyMarketTechnicalUniverseV4Receipt.from_json(raw)
                if receipt.identity_sha256 != remainder[:-5]:
                    _fail("catalog_receipt_path_identity_mismatch")
                body = receipt.to_dict()
                if body["generation_identity_sha256"] != generation_name:
                    _fail("catalog_receipt_generation_mismatch")
                plan, plan_sha, plan_error = self._load_plan(
                    generation_name,
                    by_relative,
                    plan_cache,
                )
                if plan is None or plan_error is not None or plan_sha is None:
                    _fail(plan_error or "catalog_plan_missing")
                if body["plan_identity_sha256"] != plan.identity_sha256:
                    _fail("catalog_receipt_plan_mismatch")
                if receipt.status not in _TERMINAL_STATUSES:
                    return None

                plan_body = plan.to_dict()
                cohort = plan_body["cohort"]
                if not isinstance(cohort, Mapping):
                    _fail("catalog_plan_cohort_invalid")
                counts = DailyMarketTechnicalUniverseV4Counts.from_dict(body["counts"])
                declared = cohort.get("declared_stock_codes")
                included = cohort.get("included_stock_codes")
                excluded = cohort.get("excluded_stock_codes")
                if (
                    not isinstance(declared, list)
                    or not isinstance(included, list)
                    or not isinstance(excluded, list)
                    or counts.declared_count != len(declared)
                    or counts.included_count != len(included)
                    or counts.excluded_count != len(excluded)
                ):
                    _fail("catalog_counts_cohort_mismatch")
                return DailyMarketTechnicalUniverseV4CatalogEntry(
                    generation_name=generation_name,
                    relative_path=relative_path,
                    metadata_state="metadata_unverified",
                    source_status=cast(
                        Literal["complete", "cancelled", "failed"],
                        receipt.status,
                    ),
                    generation_identity_sha256=generation_name,
                    plan_identity_sha256=plan.identity_sha256,
                    plan_bytes_sha256=plan_sha,
                    receipt_identity_sha256=receipt.identity_sha256,
                    receipt_bytes_sha256=receipt_sha,
                    source_clock_identity_sha256=cast(
                        str,
                        plan_body["source_clock_identity_sha256"],
                    ),
                    method_contracts_sha256=cast(
                        str,
                        plan_body["method_contracts_sha256"],
                    ),
                    decision_date=_parse_date(cast(object, cohort.get("decision_date"))),
                    universe_id=cast(str, cohort["universe_id"]),
                    population_version=cast(str, cohort["population_version"]),
                    cohort_identity_sha256=cast(
                        str,
                        cohort["cohort_identity_sha256"],
                    ),
                    counts=counts,
                    population_state=_population_state(cohort),
                    diagnostic_code=None,
                )
            except (DailyMarketTechnicalUniverseV4StoreError, OSError, ValueError) as exc:
                return self._entry(
                    generation_name,
                    relative_path,
                    diagnostic_code=getattr(exc, "code", "catalog_receipt_invalid"),
                )

        item = by_relative.get(relative_path)
        return self._entry(
            generation_name,
            relative_path,
            diagnostic_code=(item.diagnostic_code if item else None)
            or "catalog_unexpected_generation_entry",
        )

    def _load_plan(
        self,
        generation_name: str,
        by_relative: Mapping[str, _InventoryEntry],
        cache: dict[
            str,
            tuple[DailyMarketTechnicalUniverseV4Plan | None, str | None, str | None],
        ],
    ) -> tuple[DailyMarketTechnicalUniverseV4Plan | None, str | None, str | None]:
        if generation_name in cache:
            return cache[generation_name]
        relative_path = f"generations/{generation_name}/plan.json"
        item = by_relative.get(relative_path)
        result: tuple[DailyMarketTechnicalUniverseV4Plan | None, str | None, str | None]
        if item is None:
            result = (None, None, "catalog_plan_missing")
            cache[generation_name] = result
            return result
        if item.kind != "regular":
            result = (None, None, item.diagnostic_code or "catalog_plan_file_invalid")
            cache[generation_name] = result
            return result
        try:
            raw = _read_canonical_file(
                item.path,
                DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_PLAN_BYTES,
                "catalog_plan_read_failed",
            )
            self._verify_scanned_signature(item)
            plan_sha = _sha256_bytes(raw)
            if item.content_sha256 != plan_sha:
                _fail("catalog_metadata_bytes_changed_during_scan")
            plan = DailyMarketTechnicalUniverseV4Plan.from_json(raw)
            if plan.generation_identity_sha256 != generation_name:
                _fail("catalog_plan_generation_mismatch")
            result = (plan, plan_sha, None)
        except (DailyMarketTechnicalUniverseV4StoreError, OSError, ValueError) as exc:
            result = (None, None, getattr(exc, "code", "catalog_plan_invalid"))
        cache[generation_name] = result
        return result

    def _verify_scanned_signature(self, item: _InventoryEntry) -> None:
        current = _lstat_optional(item.path)
        if current is None or _stat_signature(current) != item.signature or _is_link_or_reparse(current):
            _fail("catalog_entry_changed_during_scan")

    def _entry(
        self,
        generation_name: str,
        relative_path: str,
        *,
        diagnostic_code: str,
    ) -> DailyMarketTechnicalUniverseV4CatalogEntry:
        return DailyMarketTechnicalUniverseV4CatalogEntry(
            generation_name=generation_name,
            relative_path=relative_path,
            metadata_state="diagnostic",
            source_status=None,
            generation_identity_sha256=None,
            plan_identity_sha256=None,
            plan_bytes_sha256=None,
            receipt_identity_sha256=None,
            receipt_bytes_sha256=None,
            source_clock_identity_sha256=None,
            method_contracts_sha256=None,
            decision_date=None,
            universe_id=None,
            population_version=None,
            cohort_identity_sha256=None,
            counts=None,
            population_state=None,
            diagnostic_code=diagnostic_code,
        )

    def _encode_cursor(self, inventory_sha256: str, generation_name: str, relative_path: str) -> str:
        body: dict[str, object] = {
            "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_V4_CATALOG_CURSOR_SCHEMA,
            "output_root": str(self.output_root),
            "inventory_sha256": inventory_sha256,
            "last_generation_name": generation_name,
            "last_relative_path": relative_path,
        }
        body["cursor_sha256"] = _sha256_bytes(_canonical_json(body).encode("utf-8"))
        raw = _canonical_json(body).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    def _decode_cursor(self, cursor: str) -> tuple[str, str, str]:
        if not isinstance(cursor, str) or not cursor or len(cursor) > 8192:
            _fail("technical_universe_v4_catalog_cursor_invalid")
        try:
            encoded = cursor.encode("ascii")
            padded = encoded + b"=" * ((4 - len(encoded) % 4) % 4)
            raw = base64.urlsafe_b64decode(padded)
            if base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") != cursor:
                _fail("technical_universe_v4_catalog_cursor_invalid")
            parsed = _parse_json(raw, limit=4096, code="technical_universe_v4_catalog_cursor_invalid")
        except (UnicodeEncodeError, ValueError, TypeError) as exc:
            raise DailyMarketTechnicalUniverseV4CatalogError("technical_universe_v4_catalog_cursor_invalid") from exc
        if not isinstance(parsed, Mapping) or set(parsed) != _CURSOR_KEYS:
            _fail("technical_universe_v4_catalog_cursor_invalid")
        body = dict(parsed)
        identity = body.pop("cursor_sha256")
        if (
            body["schema_version"] != DAILY_MARKET_TECHNICAL_UNIVERSE_V4_CATALOG_CURSOR_SCHEMA
            or body["output_root"] != str(self.output_root)
            or not _is_sha256(body["inventory_sha256"])
            or not isinstance(body["last_generation_name"], str)
            or not isinstance(body["last_relative_path"], str)
            or not isinstance(identity, str)
            or _sha256_bytes(_canonical_json(body).encode("utf-8")) != identity
        ):
            _fail("technical_universe_v4_catalog_cursor_invalid")
        return (
            cast(str, body["last_generation_name"]),
            cast(str, body["last_relative_path"]),
            cast(str, body["inventory_sha256"]),
        )


def _entry_key(entry: DailyMarketTechnicalUniverseV4CatalogEntry) -> tuple[str, str]:
    return entry.generation_name, entry.relative_path


def _generation_for_relative(relative_path: str) -> str:
    parts = relative_path.split("/")
    return parts[1] if len(parts) > 1 and parts[0] == "generations" else ""


def _parse_date(value: object) -> date:
    if not isinstance(value, str):
        _fail("catalog_decision_date_invalid")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise DailyMarketTechnicalUniverseV4CatalogError("catalog_decision_date_invalid") from exc
    if parsed.isoformat() != value:
        _fail("catalog_decision_date_invalid")
    return parsed


def _population_state(cohort: Mapping[str, object]) -> Literal["included", "all_excluded", "empty"]:
    declared = cohort.get("declared_stock_codes")
    included = cohort.get("included_stock_codes")
    excluded = cohort.get("excluded_stock_codes")
    if not isinstance(declared, list) or not isinstance(included, list) or not isinstance(excluded, list):
        _fail("catalog_cohort_population_invalid")
    if not declared:
        return "empty"
    if not included and len(excluded) == len(declared):
        return "all_excluded"
    return "included"


def _stat_signature(info: os.stat_result | None) -> tuple[int, int, int, int, int, int, int, int]:
    if info is None:
        return (0, 0, 0, 0, 0, 0, 0, 0)
    attrs = int(getattr(info, "st_file_attributes", 0))
    return (
        int(info.st_mode),
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_size),
        int(info.st_mtime_ns),
        int(info.st_ctime_ns),
        int(info.st_nlink),
        attrs,
    )


def _metadata_file_limit(relative_path: str) -> int | None:
    parts = relative_path.split("/")
    if len(parts) == 3 and parts[0] == "generations" and parts[2] == "plan.json":
        return DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_PLAN_BYTES
    if len(parts) >= 4 and parts[0] == "generations" and parts[2] == "receipts":
        return DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_RECEIPT_BYTES
    return None


def _inventory_identity(
    output_root: Path,
    root_exists: bool,
    entries: tuple[_InventoryEntry, ...] | list[_InventoryEntry],
) -> str:
    body = {
        "schema_version": "daily-market-technical-universe-v4-catalog-inventory.v1",
        "output_root": str(output_root),
        "store_exists": root_exists,
        "entries": [
            {
                "relative_path": entry.relative_path,
                "kind": entry.kind,
                "signature": list(entry.signature),
                "diagnostic_code": entry.diagnostic_code,
                "content_sha256": entry.content_sha256,
            }
            for entry in entries
        ],
    }
    return _sha256_bytes(_canonical_json(body).encode("utf-8"))
