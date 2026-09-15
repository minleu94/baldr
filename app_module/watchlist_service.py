"""
觀察清單服務 (Watchlist Service)
管理跨 Tab 共用的股票觀察清單
"""

import json
import hashlib
import os
from pathlib import Path
from typing import Any, List, Dict, Optional, Set
from datetime import date, datetime
from contextlib import closing
import sqlite3
from uuid import uuid4
import pandas as pd
from data_module.watchlist_repository import WatchlistRepository
from data_module.watchlist_migration import migrate_watchlist_copy
from app_module.dtos.decision_continuity_dtos import DecisionIdentity
from dataclasses import dataclass, asdict, field


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
        return cls(
            stock_code=stock_code,
            stock_name=str(data.get("stock_name", data.get("證券名稱", stock_code)) or stock_code),
            added_at=str(data.get("added_at", "") or ""),
            source=str(data.get("source", "manual") or "manual"),
            notes=str(data.get("notes", "") or ""),
            tags=list(data.get("tags", []) or []),
            source_id=str(data.get("source_id", "") or ""),
            decision_identity=DecisionIdentity.from_mapping(
                data,
                default_stock_code=stock_code,
            ),
        )


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

    @property
    def is_repository(self) -> bool:
        return self.mode == "repository"


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
        self.repository = repository
        # 儲存在 output_root/watchlist/
        self.watchlist_dir = config.resolve_output_path('watchlist')
        self.watchlist_dir.mkdir(parents=True, exist_ok=True)
        
        # 預設觀察清單檔案
        self.default_watchlist_file = self.watchlist_dir / "default.json"
        self.canonical_repository_path = self.repository_path(config)
        self._storage_status = storage_status or self._legacy_storage_status()
        
        # 載入預設觀察清單
        self._ensure_default_watchlist()
        if storage_status is None and self.repository is None:
            self._storage_status = self._legacy_storage_status()
        elif self.repository is None and not self._storage_status.upgrade_available:
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

        return tuple(sorted(Path(repository_path).parent.glob("*.json")))

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
        """以唯讀方式確認 canonical schema；啟動時不建立或升級 DB。"""

        if not path.is_file():
            return False
        try:
            with closing(
                sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
            ) as conn:
                conn.execute("PRAGMA query_only=ON")
                tables = {
                    str(row[0])
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                if not {"watchlists", "watchlist_revisions"}.issubset(tables):
                    return False
                watchlist_columns = {
                    str(row[1])
                    for row in conn.execute("PRAGMA table_info(watchlists)")
                }
                revision_columns = {
                    str(row[1])
                    for row in conn.execute(
                        "PRAGMA table_info(watchlist_revisions)"
                    )
                }
                return {
                    "watchlist_id",
                    "payload_json",
                    "revision",
                    "source_hash",
                    "is_deleted",
                    "last_revision_id",
                }.issubset(watchlist_columns) and {
                    "revision_id",
                    "watchlist_id",
                    "revision",
                    "operation",
                    "payload_json",
                    "payload_hash",
                    "source_hash",
                    "identity_status",
                    "continuity_event_id",
                    "revision_of",
                    "created_at",
                }.issubset(revision_columns)
        except sqlite3.Error:
            return False

    @classmethod
    def discover_repository(
        cls, config
    ) -> tuple[WatchlistRepository | None, WatchlistStorageStatus]:
        """發現既有 canonical DB；只讀檢查，不在啟動時觸發 migration。"""

        repository_path = cls.repository_path(config)
        legacy_path = repository_path.with_name("default.json")
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

    @staticmethod
    def _validate_legacy_payload(payload: Any) -> None:
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ValueError("候選池 JSON 缺有效 items")
        codes: list[str] = []
        required = ("stock_code", "stock_name", "added_at", "source")
        for item in payload["items"]:
            if not isinstance(item, dict) or not all(
                isinstance(item.get(key), str) and item[key].strip()
                for key in required
            ):
                raise ValueError("候選池存在不可遷移的項目")
            codes.append(item["stock_code"].strip())
        if len(set(codes)) != len(codes):
            raise ValueError("候選池存在重複股票身份")

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
        staged_path: Path | None = None
        activated = False
        try:
            for source in sources:
                raw = source.read_bytes()
                payload = json.loads(raw.decode("utf-8-sig"))
                self._validate_legacy_payload(payload)
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
                    migrate_watchlist_copy(
                        source,
                        staged_path,
                        sandbox_root=self.watchlist_dir.parent,
                        watchlist_id=source.stem,
                    )

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
        watchlist_file = self._watchlist_file(watchlist_id)
        watchlist.updated_at = datetime.now().isoformat()
        data = {"version": 1, "name": watchlist.name, "description": watchlist.description,
                "created_at": watchlist.created_at, "updated_at": watchlist.updated_at,
                "items": [asdict(item) for item in watchlist.items]}
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
        # 同目錄原子取代；不先搬走來源，失敗仍保留既有有效 JSON。
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
            }
            for item in watchlist.items
        ]

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
        """
        刪除觀察清單
        
        Args:
            watchlist_id: 觀察清單ID
        
        Returns:
            是否成功刪除
        """
        # 不允許刪除預設清單
        if watchlist_id == "default":
            return False
        
        watchlist_file = self._watchlist_file(watchlist_id)
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

