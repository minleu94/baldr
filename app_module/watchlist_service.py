"""
觀察清單服務 (Watchlist Service)
管理跨 Tab 共用的股票觀察清單
"""

import json
import hashlib
import os
from pathlib import Path
from typing import Any, List, Dict, Optional, Set, Literal, Mapping
from datetime import date, datetime
from contextlib import closing
import sqlite3
from uuid import uuid4
import pandas as pd
from data_module.watchlist_repository import WatchlistRepository
from data_module.watchlist_migration import migrate_watchlist_copy
from app_module.watchlist_cow_activation import (
    cow_activation_marker_path,
    resolve_watchlist_sqlite_activation,
    watchlist_service_writer_guard,
)
from app_module.dtos.decision_continuity_dtos import DecisionIdentity
from dataclasses import dataclass, asdict, field
from app_module.daily_market_research_bookmark import (
    DAILY_MARKET_RESEARCH_BOOKMARK_SOURCE,
    ORIGINAL_STOCK_RANKING_BOOKMARK_SOURCE,
    DailyMarketResearchBookmark,
    DailyMarketResearchBookmarkError,
    DailyMarketResearchBookmarkMutationResult,
    DailyMarketResearchBookmarkRestoreToken,
    OriginalStockRankingBookmark,
    decode_daily_market_research_bookmark,
)
from app_module.research_session.session_dtos import ResearchStockContextDTO
from app_module.original_stock_ranking import OriginalStockRankingError


_RESEARCH_BOOKMARK_SOURCES = frozenset(
    {DAILY_MARKET_RESEARCH_BOOKMARK_SOURCE, ORIGINAL_STOCK_RANKING_BOOKMARK_SOURCE}
)


def _bookmark_source(bookmark: Any) -> str:
    if isinstance(bookmark, OriginalStockRankingBookmark):
        return ORIGINAL_STOCK_RANKING_BOOKMARK_SOURCE
    return DAILY_MARKET_RESEARCH_BOOKMARK_SOURCE


def _rank_bookmark_error_status(code: str) -> Literal[
    "missing", "unsupported_version", "wrong_hash", "date_mismatch",
    "stock_mismatch", "source_refused",
]:
    normalized = str(code or "").lower()
    if "schema_mismatch" in normalized or "unsupported_version" in normalized:
        return "unsupported_version"
    if "hash" in normalized or "identity_mismatch" in normalized or "query_hash" in normalized:
        return "wrong_hash"
    if "date" in normalized or "parent_mismatch" in normalized:
        return "date_mismatch"
    if "stock" in normalized or "selected_row" in normalized:
        return "stock_mismatch"
    if "missing" in normalized or "not_found" in normalized:
        return "missing"
    return "source_refused"


@dataclass
class WatchlistItem:
    """觀察清單項目"""
    stock_code: str
    stock_name: str
    added_at: str
    source: str  # 'market_watch', 'recommendation', 'manual'
    notes: str = ""
    tags: Optional[List[str]] = None
    source_id: str = ""
    decision_identity: DecisionIdentity = field(default_factory=DecisionIdentity)
    research_bookmark: Any = None
    
    def __post_init__(self):
        """初始化後處理"""
        if self.tags is None:
            self.tags = []
        self.decision_identity = DecisionIdentity.from_mapping(
            self.decision_identity,
            default_stock_code=str(self.stock_code or ""),
        )
        if not self.added_at:
            self.added_at = datetime.now().isoformat()

    @classmethod
    def from_mapping(cls, data: Dict[str, Any]) -> "WatchlistItem":
        """讀取 legacy／typed item，未知欄位不會破壞舊副本。"""

        stock_code = str(data.get("stock_code", data.get("證券代號", "")) or "").strip()
        source = str(data.get("source", "manual") or "manual")
        if "research_bookmark" in data and source == "manual":
            # 收藏 payload 即使損毀也留在自己的來源命名空間，不會重新解讀為 manual/Advice。
            raw_bookmark = data.get("research_bookmark")
            source = (
                ORIGINAL_STOCK_RANKING_BOOKMARK_SOURCE
                if isinstance(raw_bookmark, dict)
                and raw_bookmark.get("schema_version") == "daily-market-research-bookmark.v2"
                else DAILY_MARKET_RESEARCH_BOOKMARK_SOURCE
            )
        return cls(
            stock_code=stock_code,
            stock_name=str(data.get("stock_name", data.get("證券名稱", stock_code)) or stock_code),
            added_at=str(data.get("added_at", "") or ""),
            source=source,
            notes=str(data.get("notes", "") or ""),
            tags=list(data.get("tags", []) or []),
            source_id=str(data.get("source_id", "") or ""),
            decision_identity=DecisionIdentity.from_mapping(
                data,
                default_stock_code=stock_code,
            ),
            research_bookmark=data.get("research_bookmark"),
        )

    def to_storage_mapping(self) -> Dict[str, Any]:
        """Serialize known fields while keeping legacy items free of null extensions."""

        payload = asdict(self)
        if self.research_bookmark is None:
            payload.pop("research_bookmark", None)
        return payload


@dataclass
class Watchlist:
    """觀察清單"""
    name: str
    items: List[WatchlistItem]
    created_at: str
    updated_at: str
    description: str = ""
    revision: int | None = None
    
    def __post_init__(self):
        """初始化後處理"""
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = datetime.now().isoformat()


@dataclass(frozen=True)
class WatchlistStorageStatus:
    """觀察清單儲存模式與一次性升級結果。"""

    mode: str
    repository_path: Path
    legacy_path: Path
    upgrade_available: bool
    message: str
    activation_marker_sha256: str | None = None

    @property
    def is_repository(self) -> bool:
        return self.mode == "repository"


@dataclass(frozen=True)
class WatchlistItemRemovalResult:
    """單一觀察清單列的精確移除結果。"""

    status: Literal["removed", "not_found", "ambiguous", "conflict"]
    code: str
    message: str
    stock_code: str
    source_id: str
    expected_source: str
    watchlist_id: str
    revision: int | None = None


@dataclass(frozen=True)
class RankResearchBookmarkReadResult:
    """rank bookmark pinned readback result for UI/report consumers."""

    status: Literal[
        "loaded",
        "missing",
        "unsupported_version",
        "wrong_hash",
        "date_mismatch",
        "stock_mismatch",
        "source_refused",
    ]
    code: str
    message: str
    bookmark_id: str
    source_id: str
    payload_sha256: str = ""
    bookmark: OriginalStockRankingBookmark | None = None
    context: ResearchStockContextDTO | None = None
    row: Mapping[str, Any] | None = None
    watchlist_revision: int | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == "loaded" and self.bookmark is not None and self.context is not None


class WatchlistService:
    """觀察清單服務"""
    
    def __init__(
        self,
        config,
        *,
        repository: WatchlistRepository | None = None,
        storage_status: WatchlistStorageStatus | None = None,
    ):
        """
        初始化觀察清單服務
        
        Args:
            config: TWStockConfig 實例
        """
        self.config = config
        # 儲存在 output_root/watchlist/
        self.watchlist_dir = config.resolve_output_path('watchlist')
        self.watchlist_dir.mkdir(parents=True, exist_ok=True)
        
        # 預設觀察清單檔案
        self.default_watchlist_file = self.watchlist_dir / "default.json"
        self.canonical_repository_path = self.repository_path(config)
        # 顯式 COW marker 即使無效，也不可退回 JSON writer。一般未遷移
        # 的 JSON 啟動流程維持原樣；只有 marker 已存在時才做此額外 discovery。
        if cow_activation_marker_path(
            self.canonical_repository_path
        ).exists():
            repository, storage_status = self.discover_repository(config)
        self.repository = repository
        self._storage_status = storage_status or self._legacy_storage_status()
        
        # 載入預設觀察清單
        if self._storage_status.mode != "blocked":
            self._ensure_default_watchlist()
        if storage_status is None and self.repository is None:
            self._storage_status = self._legacy_storage_status()
        elif (
            self.repository is None
            and self._storage_status.mode != "blocked"
            and not self._storage_status.upgrade_available
        ):
            # discover_repository 可能在預設 JSON 尚不存在時先回報 legacy；
            # _ensure_default_watchlist 完成後只更新提示，不觸發 migration。
            self._storage_status = self._legacy_storage_status(
                message=self._storage_status.message
            )

    @staticmethod
    def repository_path(config) -> Path:
        """回傳既有 OUTPUT_ROOT/watchlist 下的 canonical SQLite 路徑。"""

        output_root = getattr(config, "output_root", None)
        if output_root is None:
            raise ValueError("觀察清單需要 config.output_root")
        return Path(output_root).resolve() / "watchlist" / "watchlists.db"

    @staticmethod
    def activation_marker_path(repository_path: Path) -> Path:
        """回傳 migration 完成後的 durable activation marker 路徑。"""

        path = Path(repository_path)
        return path.with_name(f"{path.name}.active")

    @classmethod
    def _legacy_source_paths(cls, repository_path: Path) -> tuple[Path, ...]:
        """列出 bounded upgrade 會處理的原始 JSON；只讀，不建立檔案。"""

        ignored_suffixes = (".cow-conversion.v1.json", ".cow-active.json")
        return tuple(sorted(
            path
            for path in Path(repository_path).parent.glob("*.json")
            if not path.name.endswith(ignored_suffixes)
            and ".cow-rollback." not in path.name
        ))

    @classmethod
    def _read_activation_marker(cls, repository_path: Path) -> dict[str, Any] | None:
        marker_path = cls.activation_marker_path(repository_path)
        if not marker_path.is_file():
            return None
        try:
            payload = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get("schema_version") != "watchlist-activation.v1":
            return None
        if payload.get("status") != "complete":
            return None
        source_hashes = payload.get("source_hashes")
        if not isinstance(source_hashes, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in source_hashes.items()
        ):
            return None
        return payload

    @classmethod
    def _canonical_is_active(
        cls, repository_path: Path, legacy_sources: tuple[Path, ...]
    ) -> bool:
        """只接受完整啟用；無 JSON 的既有 V2 DB 保留明確相容讀取。"""

        if not cls._repository_is_ready(repository_path):
            return False
        marker_path = cls.activation_marker_path(repository_path)
        if marker_path.exists():
            return cls._read_activation_marker(repository_path) is not None
        # Increment A 已存在且沒有 legacy 副本的 DB 沒有 marker，仍可作為
        # 明確的既有 schema 相容來源；只要原 JSON 還在，就必須等完整啟用。
        return not legacy_sources

    @classmethod
    def _repository_storage_status(
        cls, repository_path: Path, legacy_path: Path
    ) -> WatchlistStorageStatus:
        return WatchlistStorageStatus(
            mode="repository",
            repository_path=repository_path,
            legacy_path=legacy_path,
            upgrade_available=False,
            message="已使用 SQLite 觀察清單；後續日常操作只寫 canonical repository。",
        )

    @classmethod
    def _repository_is_ready(cls, path: Path) -> bool:
        """只把可寫 v2 或嚴格 v3 視為 canonical repository。"""
        if not path.is_file():
            return False
        try:
            detected = WatchlistRepository(path).detect_storage_format()
        except (OSError, sqlite3.Error, ValueError):
            return False
        return detected.get("schema_version") in {2, 3} and detected.get("ready") is True

    @classmethod
    def discover_repository(
        cls, config
    ) -> tuple[WatchlistRepository | None, WatchlistStorageStatus]:
        """發現既有 canonical DB；只讀檢查，不在啟動時觸發 migration。"""

        repository_path = cls.repository_path(config)
        legacy_path = repository_path.with_name("default.json")
        explicit = resolve_watchlist_sqlite_activation(repository_path)
        if explicit.get("status") == "blocked":
            return (
                None,
                WatchlistStorageStatus(
                    mode="blocked",
                    repository_path=repository_path,
                    legacy_path=legacy_path,
                    upgrade_available=False,
                    message=(
                        "COW activation 狀態無效；已封鎖觀察清單 writer。"
                        f" ({explicit.get('code', 'invalid_explicit_marker')})"
                    ),
                ),
            )
        if explicit.get("status") == "active":
            selected_path = Path(str(explicit["repository_path"]))
            return (
                WatchlistRepository(selected_path),
                WatchlistStorageStatus(
                    mode="repository",
                    repository_path=selected_path,
                    legacy_path=legacy_path,
                    upgrade_available=False,
                    message="已由明示 COW activation 指向 SQLite v3；原來源與目標庫均保留。",
                    activation_marker_sha256=str(explicit.get("marker_sha256", "")) or None,
                ),
            )
        if explicit.get("status") == "rolled_back":
            mode = str(explicit.get("mode", ""))
            if mode == "sqlite_v1_readonly":
                return (
                    WatchlistRepository(repository_path),
                    WatchlistStorageStatus(
                        mode="repository_readonly",
                        repository_path=repository_path,
                        legacy_path=legacy_path,
                        upgrade_available=False,
                        message="COW 已回復原 v1 SQLite；來源僅供唯讀，writer 已封鎖。",
                        activation_marker_sha256=str(explicit.get("marker_sha256", "")) or None,
                    ),
                )
            if mode == "sqlite_v2":
                return (
                    WatchlistRepository(repository_path),
                    WatchlistStorageStatus(
                        mode="repository",
                        repository_path=repository_path,
                        legacy_path=legacy_path,
                        upgrade_available=False,
                        message="COW 已回復原 v2 SQLite 指向；來源 bytes 保留。",
                        activation_marker_sha256=str(explicit.get("marker_sha256", "")) or None,
                    ),
                )
            if mode == "legacy_json":
                legacy_sources = cls._legacy_source_paths(repository_path)
                return (
                    None,
                    WatchlistStorageStatus(
                        mode="upgrade_available" if legacy_sources else "legacy_json",
                        repository_path=repository_path,
                        legacy_path=legacy_path,
                        upgrade_available=bool(legacy_sources),
                        message="COW 已回復原 JSON 指向；SQLite 來源與 v3 目標均保留。",
                        activation_marker_sha256=str(explicit.get("marker_sha256", "")) or None,
                    ),
                )
            return (
                None,
                WatchlistStorageStatus(
                    mode="blocked",
                    repository_path=repository_path,
                    legacy_path=legacy_path,
                    upgrade_available=False,
                    message="COW rollback mode 不受支援；已封鎖 writer。",
                ),
            )
        legacy_sources = cls._legacy_source_paths(repository_path)
        if cls._canonical_is_active(repository_path, legacy_sources):
            return (
                WatchlistRepository(repository_path),
                cls._repository_storage_status(repository_path, legacy_path),
            )
        if cls._repository_is_ready(repository_path):
            if cls.activation_marker_path(repository_path).exists():
                message = (
                    "SQLite schema 可讀但 activation marker 無效；目前保留原 JSON，"
                    "未切換 writer。"
                )
            else:
                message = (
                    "SQLite schema 可讀但尚未完成 activation；目前保留原 JSON，"
                    "未切換 writer。"
                )
        elif repository_path.exists():
            message = "SQLite 觀察清單尚未通過 schema 檢查；目前保留原 JSON，未切換。"
        else:
            message = "目前沿用原 JSON 觀察清單；可由頁面按一次「升級觀察清單儲存」。"
        return (
            None,
            WatchlistStorageStatus(
                mode="upgrade_available" if legacy_sources else "legacy_json",
                repository_path=repository_path,
                legacy_path=legacy_path,
                upgrade_available=bool(legacy_sources),
                message=message,
            ),
        )

    def _legacy_storage_status(self, *, message: str | None = None) -> WatchlistStorageStatus:
        available = bool(self._legacy_source_paths(self.canonical_repository_path))
        return WatchlistStorageStatus(
            mode="upgrade_available" if available else "legacy_json",
            repository_path=self.canonical_repository_path,
            legacy_path=self.default_watchlist_file,
            upgrade_available=available,
            message=message
            or (
                "目前沿用原 JSON 觀察清單；可由頁面按一次「升級觀察清單儲存」。"
                if available
                else "目前使用 JSON 觀察清單；尚未有可升級的既有檔案。"
            ),
        )

    def get_storage_status(self) -> WatchlistStorageStatus:
        """回傳 UI 可核對的目前儲存模式。"""

        return self._storage_status

    def _require_active_writer(self) -> None:
        """封鎖損毀 explicit state 與回復後的 v1 唯讀來源。"""

        if self._storage_status.mode == "blocked":
            raise RuntimeError("watchlist_activation_blocked: explicit activation state 無效")
        if self._storage_status.mode == "repository_readonly":
            raise RuntimeError("watchlist_storage_readonly: 原 v1 repository 僅供讀取")

    @staticmethod
    def _validate_legacy_payload(payload: Any) -> frozenset[str]:
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ValueError("候選池 JSON 缺有效 items")
        non_bookmark_codes: set[str] = set()
        bookmark_ids: set[str] = set()
        required = ("stock_code", "stock_name", "added_at", "source")
        for item in payload["items"]:
            if not isinstance(item, dict) or not all(
                isinstance(item.get(key), str) and item[key].strip()
                for key in required
            ):
                raise ValueError("候選池存在不可遷移的項目")
            code = item["stock_code"].strip()
            is_bookmark = item.get("source") in _RESEARCH_BOOKMARK_SOURCES
            if is_bookmark or "research_bookmark" in item:
                if not is_bookmark:
                    raise ValueError("研究收藏 source 欄位不符；拒絕 fallback 或升級")
                try:
                    bookmark = decode_daily_market_research_bookmark(
                        item.get("research_bookmark")
                    )
                except DailyMarketResearchBookmarkError as exc:
                    raise ValueError("研究收藏 payload 無法驗證；未升級 JSON") from exc
                if (
                    item.get("source") != _bookmark_source(bookmark)
                    or bookmark.bookmark_id != item.get("source_id")
                    or bookmark.stock_code != code
                    or bookmark.stock_name != item.get("stock_name")
                    or bookmark.bookmark_id in bookmark_ids
                ):
                    raise ValueError("研究收藏身份重複或與項目不符；未升級 JSON")
                bookmark_ids.add(bookmark.bookmark_id)
                continue
            if code in non_bookmark_codes:
                raise ValueError("候選池存在重複股票身份")
            non_bookmark_codes.add(code)
        return frozenset(bookmark_ids)

    @classmethod
    def _verify_repository_payloads(
        cls,
        repository: WatchlistRepository,
        snapshots: dict[Path, tuple[bytes, dict[str, Any], str]],
    ) -> None:
        """核對所有來源 bytes、payload 與 repository source hash。"""

        for source, (raw, payload, source_hash) in snapshots.items():
            if source.read_bytes() != raw:
                raise RuntimeError("來源 JSON 在升級期間改變；未切換 writer")
            loaded = repository.load(source.stem)
            if loaded is None or loaded[0] != payload:
                raise RuntimeError(
                    f"候選池 {source.stem} 遷移後內容／source hash 比對失敗"
                )
            current = repository.get_current(source.stem)
            if current is None or str(current.get("source_hash", "")) != source_hash:
                raise RuntimeError(f"候選池 {source.stem} source hash 比對失敗")

    @classmethod
    def _activation_payload(
        cls, snapshots: dict[Path, tuple[bytes, dict[str, Any], str]]
    ) -> dict[str, Any]:
        source_hashes = {
            source.stem: source_hash
            for source, (_, _, source_hash) in snapshots.items()
        }
        return {
            "schema_version": "watchlist-activation.v1",
            "status": "complete",
            "repository_schema_version": WatchlistRepository.SCHEMA_VERSION,
            "source_hashes": dict(sorted(source_hashes.items())),
            "watchlist_ids": sorted(source_hashes),
        }

    @classmethod
    def _write_activation_marker(
        cls,
        repository_path: Path,
        payload: dict[str, Any],
    ) -> None:
        """以不覆寫方式發布 marker；失敗時 canonical 仍維持 inactive。"""

        marker_path = cls.activation_marker_path(repository_path)
        if marker_path.exists():
            try:
                existing = json.loads(marker_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise RuntimeError("activation marker 已存在但無法驗證；未覆寫") from exc
            if existing == payload:
                return
            raise RuntimeError("activation marker 已存在不同內容；禁止覆寫")

        temp_path = marker_path.with_name(f"{marker_path.name}.{uuid4().hex}.tmp")
        try:
            temp_path.write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            try:
                os.link(temp_path, marker_path)
            except FileExistsError as exc:
                raise RuntimeError("activation marker 同時被建立；未覆寫") from exc
            except OSError as exc:
                raise RuntimeError("無法以不覆寫方式建立 activation marker") from exc
        finally:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _publish_staged_repository(staged_path: Path, repository_path: Path) -> None:
        """以 atomic hard-link 發布新 DB，任何既有目標都不覆寫。"""

        if repository_path.exists():
            raise RuntimeError("canonical repository 已存在；禁止覆寫")
        try:
            os.link(staged_path, repository_path)
        except FileExistsError as exc:
            raise RuntimeError("canonical repository 同時被建立；禁止覆寫") from exc
        except OSError as exc:
            raise RuntimeError("無法以不覆寫方式啟用 staged repository") from exc
        try:
            staged_path.unlink()
        except OSError as exc:
            # canonical hard-link 已發布；保留它，讓下次可透過 marker recovery
            # 重試，並把本次結果明確標成未完成，而不是宣稱升級成功。
            raise RuntimeError("staged repository 暫存檔清理失敗；尚未完成啟用") from exc

    def upgrade_to_repository(self) -> WatchlistStorageStatus:
        """經使用者明確按鈕後，bounded migrate 所有 JSON 清單至同一 DB。

        所有來源先完整預檢，實際 migration 只讀來源並保留原 bytes；任何
        失敗都不切換 service writer，原 JSON 仍是可用來源，可再次重試。
        """

        self._require_active_writer()
        legacy_sources = self._legacy_source_paths(self.canonical_repository_path)
        if self.repository is not None:
            self._storage_status = self._repository_storage_status(
                self.canonical_repository_path, self.default_watchlist_file
            )
            return self._storage_status

        # 啟動或上一輪成功後的 re-open 只採用已完成 marker；不再重跑 JSON。
        if self._canonical_is_active(self.canonical_repository_path, legacy_sources):
            self.repository = WatchlistRepository(self.canonical_repository_path)
            self._storage_status = self._repository_storage_status(
                self.canonical_repository_path, self.default_watchlist_file
            )
            return self._storage_status

        sources = legacy_sources
        if not sources:
            self._storage_status = self._legacy_storage_status(
                message="沒有可升級的 JSON 觀察清單；尚未切換儲存模式。"
            )
            return self._storage_status

        snapshots: dict[Path, tuple[bytes, dict[str, Any], str]] = {}
        bookmark_ids_by_source: dict[Path, frozenset[str]] = {}
        staged_path: Path | None = None
        activated = False
        try:
            for source in sources:
                raw = source.read_bytes()
                payload = json.loads(raw.decode("utf-8-sig"))
                bookmark_ids_by_source[source] = self._validate_legacy_payload(payload)
                snapshots[source] = (raw, payload, hashlib.sha256(raw).hexdigest())

            if self.canonical_repository_path.exists():
                if not self._repository_is_ready(self.canonical_repository_path):
                    raise RuntimeError("已有 canonical DB 未通過 schema；禁止覆寫")
                # 允許在 marker 尚未落盤的中斷點做安全 recovery，但必須完整
                # 核對所有來源與 source hash，不能把 partial DB 當成成功。
                repository = WatchlistRepository(self.canonical_repository_path)
                self._verify_repository_payloads(repository, snapshots)
                self._write_activation_marker(
                    self.canonical_repository_path,
                    self._activation_payload(snapshots),
                )
                activated = True
            else:
                staged_path = self.canonical_repository_path.with_name(
                    f"{self.canonical_repository_path.name}.migration-{uuid4().hex}.tmp"
                )
                for source in sources:
                    migration_kwargs: dict[str, Any] = {
                        "sandbox_root": self.watchlist_dir.parent,
                        "watchlist_id": source.stem,
                    }
                    if bookmark_ids_by_source[source]:
                        migration_kwargs["validated_bookmark_ids"] = (
                            bookmark_ids_by_source[source]
                        )
                    migrate_watchlist_copy(source, staged_path, **migration_kwargs)

                staged_repository = WatchlistRepository(staged_path)
                self._verify_repository_payloads(staged_repository, snapshots)
                if not self._repository_is_ready(staged_path):
                    raise RuntimeError("staged repository schema 驗證失敗")
                self._publish_staged_repository(
                    staged_path, self.canonical_repository_path
                )
                activated = True
                repository = WatchlistRepository(self.canonical_repository_path)
                self._verify_repository_payloads(repository, snapshots)
                self._write_activation_marker(
                    self.canonical_repository_path,
                    self._activation_payload(snapshots),
                )
        except Exception as exc:
            self._storage_status = self._legacy_storage_status(
                message=(
                    f"觀察清單升級失敗，仍使用原 JSON，未切換 writer：{exc}；"
                    "可核對原檔後再次重試。"
                )
            )
            return self._storage_status
        finally:
            if staged_path is not None and staged_path.exists() and not activated:
                try:
                    staged_path.unlink()
                except OSError:
                    pass

        self.repository = repository
        self._storage_status = self._repository_storage_status(
            self.canonical_repository_path, self.default_watchlist_file
        )
        self._storage_status = WatchlistStorageStatus(
            mode=self._storage_status.mode,
            repository_path=self._storage_status.repository_path,
            legacy_path=self._storage_status.legacy_path,
            upgrade_available=False,
            message="觀察清單已升級、啟用並核對成功；後續日常操作只寫 canonical SQLite repository。",
        )
        return self._storage_status

    # 提供語意清楚的相容別名，所有入口仍走同一 bounded upgrade。
    migrate_to_repository = upgrade_to_repository
    
    def _watchlist_file(self, watchlist_id: str) -> Path:
        if not watchlist_id or Path(watchlist_id).name != watchlist_id or any(char in watchlist_id for char in ("/", "\\", ":")):
            raise ValueError("無效候選池 ID")
        return self.watchlist_dir / f"{watchlist_id}.json"

    def _ensure_default_watchlist(self):
        # 讀取損毀資料時保留原檔並回報；不可自動備份改名或覆寫空清單。
        if self.repository is not None:
            return
        if not self.default_watchlist_file.exists():
            self._save_watchlist("default", Watchlist("預設觀察清單", [], datetime.now().isoformat(), datetime.now().isoformat(), "系統預設觀察清單"))

    def _load_watchlist(self, watchlist_id: str) -> Optional[Watchlist]:
        watchlist_file = self._watchlist_file(watchlist_id)
        revision = None
        if self.repository is not None:
            stored = self.repository.load(watchlist_id)
            if stored is None:
                return None
            data, revision = stored
        else:
            if not watchlist_file.exists():
                return None
            data = json.loads(watchlist_file.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise ValueError("候選池資料損毀：必須包含 items 陣列")
        if not all(isinstance(item, dict) for item in data["items"]):
            raise ValueError("候選池資料損毀：items 必須是 object")
        items = [WatchlistItem.from_mapping(item) for item in data["items"]]
        return Watchlist(name=data.get("name", "未命名清單"), items=items,
                         created_at=data.get("created_at", ""), updated_at=data.get("updated_at", ""),
                         description=data.get("description", ""), revision=revision)

    def _save_watchlist(
        self,
        watchlist_id: str,
        watchlist: Watchlist,
        *,
        operation: str = "updated",
        revision_id: str | None = None,
        continuity_event_id: str | None = None,
    ):
        self._require_active_writer()
        watchlist_file = self._watchlist_file(watchlist_id)
        watchlist.updated_at = datetime.now().isoformat()
        data = {"version": 1, "name": watchlist.name, "description": watchlist.description,
                "created_at": watchlist.created_at, "updated_at": watchlist.updated_at,
                "items": [item.to_storage_mapping() for item in watchlist.items]}
        with watchlist_service_writer_guard(
            self.canonical_repository_path,
            expected_marker_sha256=self._storage_status.activation_marker_sha256,
        ):
            if self.repository is not None:
                watchlist.revision = self.repository.save(
                    watchlist_id,
                    data,
                    expected_revision=watchlist.revision,
                    operation=operation,
                    revision_id=revision_id,
                    continuity_event_id=continuity_event_id,
                )
                return
            raw = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
            temp_file = watchlist_file.with_suffix(".json.tmp")
            temp_file.write_text(raw, encoding="utf-8")
            temp_file.replace(watchlist_file)

    def query_stock_names(self, stock_codes: List[str]) -> Dict[str, str]:
        """UI 的名稱查詢接點；只讀既有來源，不初始化市場資料庫。"""
        codes = [str(code).strip() for code in stock_codes if str(code).strip()]
        if not codes:
            return {}
        db_path = getattr(self.config, "db_file", None)
        if getattr(self.config, "use_sqlite", False) and db_path is not None and Path(db_path).is_file():
            try:
                with closing(sqlite3.connect(f"{Path(db_path).resolve().as_uri()}?mode=ro", uri=True)) as conn:
                    conn.execute("PRAGMA query_only=ON")
                    placeholders = ",".join("?" for _ in codes)
                    rows = conn.execute(f"SELECT 證券代號, 證券名稱 FROM daily_prices WHERE 證券代號 IN ({placeholders}) ORDER BY 日期", tuple(codes)).fetchall()
                    return {str(code): str(name) for code, name in rows if name and str(name).strip()}
            except sqlite3.Error:
                pass
        path = getattr(self.config, "stock_data_file", None)
        if path is None or not Path(path).is_file():
            return {}
        frame = pd.read_csv(path, dtype={"證券代號": str}, usecols=["證券代號", "證券名稱"])
        return {str(row["證券代號"]): str(row["證券名稱"]) for _, row in frame.iterrows()
                if str(row["證券代號"]) in codes and pd.notna(row["證券名稱"])}

    def get_default_watchlist(self) -> Optional[Watchlist]:
        """取得預設觀察清單"""
        return self._load_watchlist("default")
    
    def get_watchlist(self, watchlist_id: str = "default") -> Optional[Watchlist]:
        """
        取得觀察清單（包含完整 Metadata）
        
        Args:
            watchlist_id: 觀察清單ID（預設為 "default"）
        
        Returns:
            Watchlist 對象，如果不存在則返回 None
        """
        return self._load_watchlist(watchlist_id)
    
    def add_stocks(
        self,
        stocks: List[Dict[str, Any]],
        source: str = "manual",
        watchlist_id: str = "default",
        *,
        revision_id: str | None = None,
        continuity_event_id: str | None = None,
    ) -> int:
        """
        新增股票到觀察清單
        
        Args:
            stocks: 股票列表，每個項目包含 stock_code 和 stock_name
            source: 來源（'market_watch', 'recommendation', 'manual'）
            watchlist_id: 觀察清單ID（預設為 "default"）
        
        Returns:
            新增的股票數量（排除重複）
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            watchlist = self._load_watchlist(watchlist_id)
            if watchlist is None:
                watchlist = Watchlist(
                    name="預設觀察清單" if watchlist_id == "default" else watchlist_id,
                    items=[],
                    created_at=datetime.now().isoformat(),
                    updated_at=datetime.now().isoformat()
                )
            
            # 取得現有股票代號集合（避免重複）
            existing_codes = {item.stock_code for item in watchlist.items}
            
            # 新增股票
            added_count = 0
            for stock in stocks:
                try:
                    stock_code = stock.get('stock_code') or stock.get('證券代號')
                    stock_name = stock.get('stock_name') or stock.get('證券名稱', stock_code)
                    
                    # 驗證和清理數據
                    if not stock_code:
                        logger.warning(f"跳過無效的股票（缺少 stock_code）: {stock}")
                        continue
                    
                    # 確保是字符串且不為空
                    stock_code = str(stock_code).strip()
                    if not stock_code or stock_code.lower() in ['none', 'nan', '-', '']:
                        logger.warning(f"跳過無效的股票代號: {stock_code}")
                        continue
                    
                    if not stock_name:
                        stock_name = stock_code
                    else:
                        stock_name = str(stock_name).strip()
                        if not stock_name or stock_name.lower() in ['none', 'nan', '-', '']:
                            stock_name = stock_code
                    
                    identity = DecisionIdentity.from_mapping(
                        stock,
                        default_stock_code=stock_code,
                    )
                    has_explicit_candidate_identity = identity.is_linked
                    # Legacy 未帶 typed identity 時仍依股票代號去重；明確的
                    # result_id+stock_code 則依 candidate key 去重，避免同股
                    # 不同研究結果互相覆蓋。
                    duplicate = (
                        any(
                            existing.decision_identity.is_linked
                            and existing.decision_identity.candidate_key
                            == identity.candidate_key
                            for existing in watchlist.items
                        )
                        if has_explicit_candidate_identity
                        else stock_code in existing_codes
                    )
                    if duplicate:
                        logger.debug(f"股票 {stock_code} 已在觀察清單中，跳過")
                        continue
                    
                    # 新增項目
                    raw_tags = stock.get('tags', [])
                    tags = raw_tags if isinstance(raw_tags, list) else []
                    item = WatchlistItem(
                        stock_code=stock_code,
                        stock_name=stock_name,
                        added_at=datetime.now().isoformat(),
                        source=source,
                        notes=str(stock.get('notes', '')).strip(),
                        tags=[str(tag) for tag in tags],
                        source_id=str(stock.get("source_id") or stock.get("result_id") or ""),
                        decision_identity=identity,
                    )
                    watchlist.items.append(item)
                    existing_codes.add(stock_code)
                    added_count += 1
                    logger.debug(f"成功添加股票到觀察清單: {stock_code} ({stock_name})")
                except Exception as e:
                    logger.error(f"處理股票數據時出錯: {stock}, 錯誤: {e}")
                    continue
            
            # 儲存
            if added_count > 0:
                self._save_watchlist(
                    watchlist_id,
                    watchlist,
                    operation="added",
                    revision_id=revision_id,
                    continuity_event_id=continuity_event_id,
                )
                logger.info(f"成功添加 {added_count} 檔股票到觀察清單")
            
            return added_count
        except Exception as e:
            logger.error(f"添加股票到觀察清單失敗: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise
    
    def remove_stocks(
        self,
        stock_codes: List[str],
        watchlist_id: str = "default",
        *,
        revision_id: str | None = None,
        continuity_event_id: str | None = None,
    ) -> int:
        """
        從觀察清單移除股票
        
        Args:
            stock_codes: 要移除的股票代號列表
            watchlist_id: 觀察清單ID
        
        Returns:
            移除的股票數量
        """
        watchlist = self._load_watchlist(watchlist_id)
        if watchlist is None:
            return 0
        
        # 記錄原始數量
        original_count = len(watchlist.items)
        
        # 移除股票
        stock_codes_set = set(stock_codes)
        watchlist.items = [
            item for item in watchlist.items
            if item.stock_code not in stock_codes_set
        ]
        
        # 計算移除數量
        removed_count = original_count - len(watchlist.items)
        
        # 沒有變更時不產生空 revision，讓 retry 保持 idempotent。
        if removed_count:
            self._save_watchlist(
                watchlist_id,
                watchlist,
                operation="removed",
                revision_id=revision_id,
                continuity_event_id=continuity_event_id,
            )
        
        return removed_count
    
    def remove_watchlist_item(
        self,
        stock_code: str,
        source_id: str,
        expected_source: str,
        watchlist_id: str = "default",
        *,
        revision_id: str | None = None,
        continuity_event_id: str | None = None,
    ) -> WatchlistItemRemovalResult:
        """精確移除一列，避免同股的不同來源或研究收藏一起消失。"""

        code = str(stock_code or "").strip()
        identity = str(source_id or "").strip()
        source = str(expected_source or "").strip()
        if source in _RESEARCH_BOOKMARK_SOURCES:
            return WatchlistItemRemovalResult(
                status="conflict",
                code="use_bookmark_removal",
                message="研究收藏請使用 remove_research_bookmark(bookmark_id)。",
                stock_code=code,
                source_id=identity,
                expected_source=source,
                watchlist_id=watchlist_id,
            )
        current = self._load_watchlist(watchlist_id)
        if current is None:
            return WatchlistItemRemovalResult(
                status="not_found",
                code="watchlist_not_found",
                message="找不到觀察清單。",
                stock_code=code,
                source_id=identity,
                expected_source=source,
                watchlist_id=watchlist_id,
            )
        matches = [
            index
            for index, item in enumerate(current.items)
            if item.stock_code == code
            and item.source_id == identity
            and item.source == source
            and item.research_bookmark is None
        ]
        if len(matches) != 1:
            status: Literal["not_found", "ambiguous"] = (
                "not_found" if not matches else "ambiguous"
            )
            return WatchlistItemRemovalResult(
                status=status,
                code=f"watchlist_item_{status}",
                message=(
                    "找不到完全符合股票、來源與來源 ID 的項目。"
                    if status == "not_found"
                    else "完全符合條件的項目不只一列；未移除任何項目。"
                ),
                stock_code=code,
                source_id=identity,
                expected_source=source,
                watchlist_id=watchlist_id,
                revision=current.revision,
            )
        current.items.pop(matches[0])
        self._save_watchlist(
            watchlist_id,
            current,
            operation="item_removed",
            revision_id=revision_id,
            continuity_event_id=continuity_event_id,
        )
        return WatchlistItemRemovalResult(
            status="removed",
            code="watchlist_item_removed",
            message="已移除指定觀察清單項目。",
            stock_code=code,
            source_id=identity,
            expected_source=source,
            watchlist_id=watchlist_id,
            revision=current.revision,
        )

    def remove_stock(
        self,
        watchlist_id: str = "default",
        stock_code: str = None,
        *,
        revision_id: str | None = None,
        continuity_event_id: str | None = None,
    ) -> int:
        """
        從觀察清單移除單一股票（便捷方法）
        
        Args:
            watchlist_id: 觀察清單ID
            stock_code: 要移除的股票代號
        
        Returns:
            移除的股票數量（0 或 1）
        """
        if stock_code is None:
            return 0
        return self.remove_stocks(
            [stock_code],
            watchlist_id,
            revision_id=revision_id,
            continuity_event_id=continuity_event_id,
        )
    
    def clear_watchlist(
        self,
        watchlist_id: str = "default",
        *,
        revision_id: str | None = None,
        continuity_event_id: str | None = None,
    ) -> bool:
        """
        清空觀察清單
        
        Args:
            watchlist_id: 觀察清單ID
        
        Returns:
            是否成功清空
        """
        watchlist = self._load_watchlist(watchlist_id)
        if watchlist is None:
            return False
        
        if not watchlist.items:
            return True
        watchlist.items = []
        watchlist.updated_at = datetime.now().isoformat()
        self._save_watchlist(
            watchlist_id,
            watchlist,
            operation="cleared",
            revision_id=revision_id,
            continuity_event_id=continuity_event_id,
        )
        return True
    
    def get_stock_codes(self, watchlist_id: str = "default") -> List[str]:
        """
        取得觀察清單中的股票代號列表
        
        Args:
            watchlist_id: 觀察清單ID
        
        Returns:
            股票代號列表
        """
        watchlist = self._load_watchlist(watchlist_id)
        if watchlist is None:
            return []
        
        return [item.stock_code for item in watchlist.items]
    
    def get_stocks(self, watchlist_id: str = "default") -> List[Dict[str, Any]]:
        """
        取得觀察清單中的股票列表（包含詳細資訊）
        
        Args:
            watchlist_id: 觀察清單ID
        
        Returns:
            股票列表，每個項目包含 stock_code, stock_name, added_at, source 等
        """
        watchlist = self._load_watchlist(watchlist_id)
        if watchlist is None:
            return []
        
        return [
            {
                'stock_code': item.stock_code,
                'stock_name': item.stock_name,
                'added_at': item.added_at,
                'source': item.source,
                'notes': item.notes,
                'tags': item.tags,
                'source_id': item.source_id,
                'decision_identity': item.decision_identity.to_dict(),
                'research_bookmark': item.research_bookmark,
            }
            for item in watchlist.items
        ]

    def add_research_bookmark(
        self,
        bookmark: DailyMarketResearchBookmark | OriginalStockRankingBookmark | Dict[str, Any],
        watchlist_id: str = "default",
        *,
        revision_id: str | None = None,
        continuity_event_id: str | None = None,
    ) -> DailyMarketResearchBookmarkMutationResult:
        """保存一筆不可變研究收藏，不按股票代號去重。"""

        verified_bookmark = decode_daily_market_research_bookmark(
            bookmark.to_dict()
            if isinstance(bookmark, (DailyMarketResearchBookmark, OriginalStockRankingBookmark))
            else bookmark
        )
        expected_source = _bookmark_source(verified_bookmark)
        current = self._load_watchlist(watchlist_id)
        if current is None:
            current = Watchlist(
                name="預設觀察清單" if watchlist_id == "default" else watchlist_id,
                items=[],
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
            )

        expected_payload = verified_bookmark.to_dict()
        for item in current.items:
            raw = item.research_bookmark
            raw_id = raw.get("bookmark_id") if isinstance(raw, dict) else None
            if raw_id == verified_bookmark.bookmark_id:
                try:
                    existing = decode_daily_market_research_bookmark(raw)
                except DailyMarketResearchBookmarkError as exc:
                    return DailyMarketResearchBookmarkMutationResult(
                        status="conflict",
                        code=exc.code,
                        message="同一 bookmark_id 已有無法驗證的收藏；未覆寫。",
                        bookmark_id=verified_bookmark.bookmark_id,
                        watchlist_id=watchlist_id,
                        revision=current.revision,
                    )
                if (
                    existing.to_dict() == expected_payload
                    and item.stock_code == verified_bookmark.stock_code
                    and item.stock_name == verified_bookmark.stock_name
                    and item.source == expected_source
                    and item.source_id == verified_bookmark.bookmark_id
                ):
                    return DailyMarketResearchBookmarkMutationResult(
                        status="already_present",
                        code="bookmark_already_present",
                        message="相同研究收藏已存在，沒有新增 revision。",
                        bookmark_id=verified_bookmark.bookmark_id,
                        watchlist_id=watchlist_id,
                        revision=current.revision,
                    )
                return DailyMarketResearchBookmarkMutationResult(
                    status="conflict",
                    code="bookmark_identity_conflict",
                    message="相同 bookmark_id 對應不同內容；未覆寫既有收藏。",
                    bookmark_id=verified_bookmark.bookmark_id,
                    watchlist_id=watchlist_id,
                    revision=current.revision,
                )
            if item.source_id == verified_bookmark.bookmark_id:
                return DailyMarketResearchBookmarkMutationResult(
                    status="conflict",
                    code="bookmark_source_id_conflict",
                    message="bookmark_id 已被另一種觀察清單項目使用；未覆寫。",
                    bookmark_id=verified_bookmark.bookmark_id,
                    watchlist_id=watchlist_id,
                    revision=current.revision,
                )

        current.items.append(
            WatchlistItem(
                stock_code=verified_bookmark.stock_code,
                stock_name=verified_bookmark.stock_name,
                added_at=datetime.now().isoformat(),
                source=expected_source,
                source_id=verified_bookmark.bookmark_id,
                research_bookmark=expected_payload,
            )
        )
        self._save_watchlist(
            watchlist_id,
            current,
            operation="research_bookmark_added",
            revision_id=revision_id,
            continuity_event_id=continuity_event_id,
        )
        return DailyMarketResearchBookmarkMutationResult(
            status="added",
            code="bookmark_added",
            message="已保存每日市場研究收藏。",
            bookmark_id=verified_bookmark.bookmark_id,
            watchlist_id=watchlist_id,
            revision=current.revision,
        )

    def add_rank_research_bookmark(
        self,
        bookmark: OriginalStockRankingBookmark | Dict[str, Any],
        watchlist_id: str = "default",
        *,
        revision_id: str | None = None,
        continuity_event_id: str | None = None,
    ) -> DailyMarketResearchBookmarkMutationResult:
        """將已驗證的原始排名收藏寫入既有 Watchlist ledger。"""

        verified = decode_daily_market_research_bookmark(
            bookmark.to_dict() if isinstance(bookmark, OriginalStockRankingBookmark) else bookmark
        )
        if not isinstance(verified, OriginalStockRankingBookmark):
            raise DailyMarketResearchBookmarkError(
                "bookmark_schema_mismatch", "rank bookmark API 僅接受原始排名 v2 收藏"
            )
        return self.add_research_bookmark(
            verified,
            watchlist_id,
            revision_id=revision_id,
            continuity_event_id=continuity_event_id,
        )

    def get_research_bookmark(
        self,
        bookmark_id: str,
        watchlist_id: str = "default",
    ) -> DailyMarketResearchBookmark | OriginalStockRankingBookmark | None:
        """讀取指定收藏身份；符合 ID 但格式錯誤的 payload 會拒絕讀取。"""

        identity = str(bookmark_id or "").strip()
        if not identity:
            return None
        current = self._load_watchlist(watchlist_id)
        if current is None:
            return None
        matches = [
            item
            for item in current.items
            if isinstance(item.research_bookmark, dict)
            and item.research_bookmark.get("bookmark_id") == identity
        ]
        if not matches:
            return None
        if len(matches) != 1:
            raise DailyMarketResearchBookmarkError(
                "bookmark_identity_ambiguous", "bookmark_id 在觀察清單內重複，拒絕猜選項目。"
            )
        item = matches[0]
        if (
            item.source not in _RESEARCH_BOOKMARK_SOURCES
            or item.source_id != identity
        ):
            raise DailyMarketResearchBookmarkError(
                "bookmark_item_identity_mismatch", "收藏項目的 source/source_id 與 bookmark_id 不一致。"
            )
        bookmark = decode_daily_market_research_bookmark(item.research_bookmark)
        if item.source != _bookmark_source(bookmark):
            raise DailyMarketResearchBookmarkError(
                "bookmark_item_identity_mismatch", "bookmark source 與 schema/source 不符"
            )
        if bookmark.stock_code != item.stock_code or bookmark.stock_name != item.stock_name:
            raise DailyMarketResearchBookmarkError(
                "bookmark_item_stock_mismatch", "收藏 payload 與 watchlist item 的股票身份不一致。"
            )
        return bookmark

    def get_rank_research_bookmark_context(
        self,
        bookmark_id: str,
        *,
        db_path: str | Path,
        watchlist_id: str = "default",
    ) -> RankResearchBookmarkReadResult:
        """驗證收藏 payload 後，依 pins 唯讀取回原始排名列。"""

        identity = str(bookmark_id or "").strip()
        current = self._load_watchlist(watchlist_id)
        revision = current.revision if current is not None else None
        if not identity or current is None:
            return RankResearchBookmarkReadResult(
                status="missing", code="bookmark_not_found", message="找不到排名收藏。",
                bookmark_id=identity, source_id=identity, watchlist_revision=revision,
            )
        matches = [
            item for item in current.items
            if isinstance(item.research_bookmark, dict)
            and item.research_bookmark.get("bookmark_id") == identity
        ]
        if not matches:
            return RankResearchBookmarkReadResult(
                status="missing", code="bookmark_not_found", message="找不到排名收藏。",
                bookmark_id=identity, source_id=identity, watchlist_revision=revision,
            )
        if len(matches) != 1:
            return RankResearchBookmarkReadResult(
                status="source_refused", code="bookmark_identity_ambiguous",
                message="排名收藏身份不唯一，拒絕讀回。", bookmark_id=identity,
                source_id=identity, watchlist_revision=revision,
            )
        raw = matches[0].research_bookmark
        assert isinstance(raw, dict)
        if raw.get("schema_version") != "daily-market-research-bookmark.v2":
            return RankResearchBookmarkReadResult(
                status="unsupported_version", code="bookmark_schema_mismatch",
                message="此收藏不是支援的原始排名版本。", bookmark_id=identity,
                source_id=identity, watchlist_revision=revision,
            )
        try:
            bookmark = self.get_research_bookmark(identity, watchlist_id)
            if not isinstance(bookmark, OriginalStockRankingBookmark):
                raise DailyMarketResearchBookmarkError(
                    "bookmark_schema_mismatch", "payload 不是原始排名收藏"
                )
            rank_context = bookmark.context.rank_context
            if rank_context is None:
                raise DailyMarketResearchBookmarkError(
                    "bookmark_rank_context_missing", "排名收藏缺少 pinned context"
                )
            from app_module.original_stock_ranking import (
                read_original_stock_ranking_row_from_context,
            )

            row = read_original_stock_ranking_row_from_context(rank_context, db_path=db_path)
        except DailyMarketResearchBookmarkError as exc:
            status = _rank_bookmark_error_status(exc.code)
            return RankResearchBookmarkReadResult(
                status=status, code=exc.code, message=str(exc),
                bookmark_id=identity, source_id=identity,
                payload_sha256=str(raw.get("payload_sha256") or ""),
                watchlist_revision=revision,
            )
        except OriginalStockRankingError as exc:
            status = _rank_bookmark_error_status(exc.code)
            return RankResearchBookmarkReadResult(
                status=status, code=exc.code, message=str(exc),
                bookmark_id=identity, source_id=identity,
                payload_sha256=str(raw.get("payload_sha256") or ""),
                watchlist_revision=revision,
            )
        return RankResearchBookmarkReadResult(
            status="loaded", code="rank_bookmark_loaded",
            message="已從 pinned manifest 讀回排名來源。",
            bookmark_id=identity, source_id=identity,
            payload_sha256=bookmark.payload_sha256, bookmark=bookmark,
            context=bookmark.context, row=row, watchlist_revision=revision,
        )

    def get_research_bookmark_context(
        self,
        bookmark_id: str,
        watchlist_id: str = "default",
        *,
        db_path: str | Path | None = None,
    ):
        """以 watchlist 來源重建 pinned context，不建立 Advice 身份。"""

        bookmark = self.get_research_bookmark(bookmark_id, watchlist_id)
        if isinstance(bookmark, OriginalStockRankingBookmark):
            if db_path is None:
                raise DailyMarketResearchBookmarkError(
                    "bookmark_source_db_required", "排名收藏讀回需要明確的唯讀 DB 路徑以執行來源防護"
                )
            result = self.get_rank_research_bookmark_context(
                bookmark_id, db_path=db_path, watchlist_id=watchlist_id
            )
            if not result.succeeded or result.context is None:
                raise DailyMarketResearchBookmarkError(result.code, result.message)
            return result.context
        return bookmark.context if bookmark is not None else None

    def remove_research_bookmark(
        self,
        bookmark_id: str,
        watchlist_id: str = "default",
        *,
        revision_id: str | None = None,
        continuity_event_id: str | None = None,
    ) -> DailyMarketResearchBookmarkMutationResult:
        """只移除一筆身份完全相符的收藏，並回傳可用的復原 token。"""

        identity = str(bookmark_id or "").strip()
        if not identity:
            return DailyMarketResearchBookmarkMutationResult(
                status="not_found",
                code="bookmark_id_missing",
                message="缺少研究收藏 bookmark_id。",
                bookmark_id="",
                watchlist_id=watchlist_id,
            )
        current = self._load_watchlist(watchlist_id)
        if current is None:
            return DailyMarketResearchBookmarkMutationResult(
                status="not_found",
                code="bookmark_not_found",
                message="找不到指定研究收藏。",
                bookmark_id=identity,
                watchlist_id=watchlist_id,
            )
        matches: list[tuple[int, WatchlistItem, DailyMarketResearchBookmark | OriginalStockRankingBookmark]] = []
        for index, item in enumerate(current.items):
            raw = item.research_bookmark
            if not isinstance(raw, dict) or raw.get("bookmark_id") != identity:
                continue
            bookmark = decode_daily_market_research_bookmark(raw)
            if (
                item.source != _bookmark_source(bookmark)
                or item.source_id != identity
                or bookmark.stock_code != item.stock_code
                or bookmark.stock_name != item.stock_name
            ):
                return DailyMarketResearchBookmarkMutationResult(
                    status="conflict",
                    code="bookmark_item_identity_mismatch",
                    message="收藏列身份不一致；未移除任何項目。",
                    bookmark_id=identity,
                    watchlist_id=watchlist_id,
                    revision=current.revision,
                )
            matches.append((index, item, bookmark))
        if not matches:
            return DailyMarketResearchBookmarkMutationResult(
                status="not_found",
                code="bookmark_not_found",
                message="找不到指定研究收藏。",
                bookmark_id=identity,
                watchlist_id=watchlist_id,
                revision=current.revision,
            )
        if len(matches) != 1:
            return DailyMarketResearchBookmarkMutationResult(
                status="conflict",
                code="bookmark_identity_ambiguous",
                message="bookmark_id 重複；未移除任何項目。",
                bookmark_id=identity,
                watchlist_id=watchlist_id,
                revision=current.revision,
            )
        index, item, _bookmark = matches[0]
        token = DailyMarketResearchBookmarkRestoreToken(
            watchlist_id=watchlist_id,
            bookmark_id=identity,
            item_payload_json=json.dumps(
                item.to_storage_mapping(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
            item_index=index,
        )
        current.items.pop(index)
        self._save_watchlist(
            watchlist_id,
            current,
            operation="research_bookmark_removed",
            revision_id=revision_id,
            continuity_event_id=continuity_event_id,
        )
        return DailyMarketResearchBookmarkMutationResult(
            status="removed",
            code="bookmark_removed",
            message="已移除指定研究收藏；可用 restore_token 復原。",
            bookmark_id=identity,
            watchlist_id=watchlist_id,
            revision=current.revision,
            restore_token=token,
        )

    def restore_research_bookmark(
        self,
        token: DailyMarketResearchBookmarkRestoreToken,
        watchlist_id: str | None = None,
        *,
        revision_id: str | None = None,
        continuity_event_id: str | None = None,
    ) -> DailyMarketResearchBookmarkMutationResult:
        """依 token 回復原收藏項目，不覆寫其他項目。"""

        if not isinstance(token, DailyMarketResearchBookmarkRestoreToken):
            raise TypeError("restore_research_bookmark 需要原始 remove result 的 restore_token")
        destination = str(watchlist_id or token.watchlist_id)
        if destination != token.watchlist_id:
            return DailyMarketResearchBookmarkMutationResult(
                status="conflict",
                code="bookmark_restore_watchlist_mismatch",
                message="restore_token 只能回復到原觀察清單。",
                bookmark_id=token.bookmark_id,
                watchlist_id=destination,
            )
        try:
            payload = json.loads(token.item_payload_json)
        except (TypeError, json.JSONDecodeError) as exc:
            raise DailyMarketResearchBookmarkError(
                "bookmark_restore_token_invalid", "restore_token item payload 無法解析。"
            ) from exc
        if not isinstance(payload, dict):
            raise DailyMarketResearchBookmarkError(
                "bookmark_restore_token_invalid", "restore_token item payload 必須是 object。"
            )
        bookmark_payload = payload.get("research_bookmark")
        bookmark = decode_daily_market_research_bookmark(bookmark_payload)
        if (
            bookmark.bookmark_id != token.bookmark_id
            or payload.get("source") != _bookmark_source(bookmark)
            or payload.get("source_id") != token.bookmark_id
            or payload.get("stock_code") != bookmark.stock_code
            or payload.get("stock_name") != bookmark.stock_name
        ):
            raise DailyMarketResearchBookmarkError(
                "bookmark_restore_identity_mismatch", "restore_token 與 bookmark item identity 不一致。"
            )
        current = self._load_watchlist(destination)
        if current is None:
            return DailyMarketResearchBookmarkMutationResult(
                status="not_found",
                code="watchlist_not_found",
                message="原觀察清單已不存在，無法回復收藏。",
                bookmark_id=token.bookmark_id,
                watchlist_id=destination,
            )
        for item in current.items:
            raw = item.research_bookmark
            raw_id = raw.get("bookmark_id") if isinstance(raw, dict) else None
            if raw_id == token.bookmark_id:
                try:
                    existing = decode_daily_market_research_bookmark(raw)
                except DailyMarketResearchBookmarkError as exc:
                    return DailyMarketResearchBookmarkMutationResult(
                        status="conflict",
                        code=exc.code,
                        message="目前已有同 identity 的無效收藏；未覆寫。",
                        bookmark_id=token.bookmark_id,
                        watchlist_id=destination,
                        revision=current.revision,
                    )
                if (
                    item.source != _bookmark_source(existing)
                    or item.source_id != token.bookmark_id
                    or item.stock_code != existing.stock_code
                    or item.stock_name != existing.stock_name
                ):
                    return DailyMarketResearchBookmarkMutationResult(
                        status="conflict",
                        code="bookmark_item_identity_mismatch",
                        message="目前同 identity 收藏列的外層欄位不一致；未覆寫。",
                        bookmark_id=token.bookmark_id,
                        watchlist_id=destination,
                        revision=current.revision,
                    )
                if existing.to_dict() == bookmark.to_dict():
                    return DailyMarketResearchBookmarkMutationResult(
                        status="already_present",
                        code="bookmark_already_present",
                        message="相同研究收藏已存在，沒有新增 revision。",
                        bookmark_id=token.bookmark_id,
                        watchlist_id=destination,
                        revision=current.revision,
                    )
                return DailyMarketResearchBookmarkMutationResult(
                    status="conflict",
                    code="bookmark_identity_conflict",
                    message="同 bookmark_id 已有不同內容；未覆寫。",
                    bookmark_id=token.bookmark_id,
                    watchlist_id=destination,
                    revision=current.revision,
                )
        restored_item = WatchlistItem.from_mapping(payload)
        if (
            restored_item.source != _bookmark_source(bookmark)
            or restored_item.source_id != token.bookmark_id
            or restored_item.stock_code != bookmark.stock_code
        ):
            raise DailyMarketResearchBookmarkError(
                "bookmark_restore_identity_mismatch", "restore_token item 欄位與 bookmark payload 不一致。"
            )
        index = max(0, min(token.item_index, len(current.items)))
        current.items.insert(index, restored_item)
        self._save_watchlist(
            destination,
            current,
            operation="research_bookmark_restored",
            revision_id=revision_id,
            continuity_event_id=continuity_event_id,
        )
        return DailyMarketResearchBookmarkMutationResult(
            status="restored",
            code="bookmark_restored",
            message="已回復指定研究收藏。",
            bookmark_id=token.bookmark_id,
            watchlist_id=destination,
            revision=current.revision,
        )

    def bind_stock_decision_identity(
        self,
        stock_code: str,
        decision_identity: DecisionIdentity | Dict[str, Any],
        *,
        expected_source_id: str = "",
        watchlist_id: str = "default",
        revision_id: str | None = None,
        continuity_event_id: str | None = None,
    ) -> bool:
        """把使用者明確選定的推薦來源寫回既有候選池項目。

        這是 legacy／unknown item 的 explicit repair path；若同股有多列且
        無法用既有 source_id 唯一定位，直接拒絕，不以最新結果或第一列猜測。
        """

        code = str(stock_code or "").strip()
        if not code:
            return False
        identity = DecisionIdentity.from_mapping(
            decision_identity,
            default_stock_code=code,
        )
        if not identity.is_linked:
            raise ValueError("需要完整的 result_id + stock_code 才能綁定推薦來源")

        watchlist = self._load_watchlist(watchlist_id)
        if watchlist is None:
            return False
        candidates = [item for item in watchlist.items if item.stock_code == code]
        expected_source = str(expected_source_id or "").strip()
        if expected_source:
            candidates = [item for item in candidates if item.source_id == expected_source]
        if len(candidates) != 1:
            return False
        item = candidates[0]
        if item.decision_identity.is_linked and item.decision_identity != identity:
            raise ValueError("候選池既有推薦來源與選定來源衝突")
        if item.decision_identity == identity:
            return True
        item.decision_identity = identity
        # 保留既有 lineage；legacy 空值則填入已驗證的 result_id，讓舊顯示與
        # 新 typed identity 都能在重啟後讀回同一來源。
        if not item.source_id:
            item.source_id = identity.result_id
        self._save_watchlist(
            watchlist_id,
            watchlist,
            operation="identity_bound",
            revision_id=revision_id,
            continuity_event_id=continuity_event_id,
        )
        return True

    def list_watchlist_revisions(self, watchlist_id: str = "default") -> List[Dict[str, Any]]:
        """讀取 repository 歷史；JSON legacy writer 沒有虛構 history。"""

        if self.repository is None:
            return []
        return self.repository.list_revisions(watchlist_id)
    
    def list_watchlists(self) -> List[Dict[str, Any]]:
        """
        列出所有觀察清單
        
        Returns:
            觀察清單列表，每個項目包含 watchlist_id, name, item_count 等
        """
        watchlists = []
        ids = self.repository.list_ids() if self.repository is not None else [path.stem for path in self.watchlist_dir.glob("*.json")]
        for watchlist_id in ids:
            try:
                watchlist = self._load_watchlist(watchlist_id)
                if watchlist:
                    watchlists.append({
                        'watchlist_id': watchlist_id,
                        'name': watchlist.name,
                        'item_count': len(watchlist.items),
                        'created_at': watchlist.created_at,
                        'updated_at': watchlist.updated_at,
                        'description': watchlist.description
                    })
            except:
                continue
        
        return watchlists
    
    def create_watchlist(
        self,
        name: str,
        description: str = ""
    ) -> str:
        """
        建立新的觀察清單
        
        Args:
            name: 清單名稱
            description: 描述
        
        Returns:
            觀察清單ID
        """
        # 生成ID（使用時間戳）
        watchlist_id = f"watchlist_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        watchlist = Watchlist(
            name=name,
            items=[],
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            description=description
        )
        
        self._save_watchlist(watchlist_id, watchlist)
        
        return watchlist_id
    
    def delete_watchlist(
        self,
        watchlist_id: str,
        *,
        revision_id: str | None = None,
        continuity_event_id: str | None = None,
    ) -> bool:
        self._require_active_writer()
        if watchlist_id == "default":
            return False
        watchlist_file = self._watchlist_file(watchlist_id)
        with watchlist_service_writer_guard(
            self.canonical_repository_path,
            expected_marker_sha256=self._storage_status.activation_marker_sha256,
        ):
            if self.repository is not None:
                loaded = self.repository.load(watchlist_id)
                return (
                    self.repository.delete(
                        watchlist_id,
                        expected_revision=loaded[1],
                        revision_id=revision_id,
                        continuity_event_id=continuity_event_id,
                    )
                    if loaded
                    else False
                )
            if watchlist_file.exists():
                watchlist_file.unlink()
                return True
            return False
