from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
import logging
import shutil
import os
import argparse
import sys
import re


def _optional_env_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    return Path(value) if value else None


def _technical_universe_read_root_from_environment() -> Path | None:
    name = "TECHNICAL_UNIVERSE_READ_ROOT"
    if name not in os.environ:
        return None
    value = os.environ[name].strip()
    if not value:
        raise ValueError("TECHNICAL_UNIVERSE_READ_ROOT 必須是非空絕對路徑")
    return Path(value)


def _fundamental_read_snapshot_root_from_environment() -> Path | None:
    name = "FUNDAMENTAL_READ_SNAPSHOT_ROOT"
    if name not in os.environ:
        return None
    value = os.environ[name].strip()
    if not value:
        raise ValueError("FUNDAMENTAL_READ_SNAPSHOT_ROOT 必須是非空絕對路徑")
    return Path(value)


def _personal_h20_sqlite_read_root_from_environment() -> Path | None:
    name = "PERSONAL_H20_SQLITE_READ_ROOT"
    if name not in os.environ:
        return None
    value = os.environ[name].strip()
    if not value:
        raise ValueError("PERSONAL_H20_SQLITE_READ_ROOT 必須是非空絕對路徑")
    return Path(value)


@dataclass
class TWStockConfig:
    """台股數據分析核心配置"""
    
    # 基礎路徑配置 - 支持環境變量和CLI覆蓋
    data_root: Path = field(default_factory=lambda: Path(
        os.environ.get('DATA_ROOT', 'D:/Min/Python/Project/FA_Data')
    ))
    output_root: Path = field(default_factory=lambda: Path(
        os.environ.get('OUTPUT_ROOT', 'D:/Min/Python/Project/FA_Data/output')
    ))
    profile: str = field(default_factory=lambda: os.environ.get('PROFILE', 'prod'))
    
    # 保持向後兼容的base_dir屬性
    base_dir: Path = field(init=False)
    
    # 數據目錄
    data_dir: Path = field(init=False)
    daily_price_dir: Path = field(init=False)
    tpex_daily_price_dir: Path = field(init=False)
    meta_data_dir: Path = field(init=False)
    technical_dir: Path = field(init=False)
    log_dir: Path = field(init=False)  # 應用程式執行日誌目錄
    sqlite_dir: Path = field(init=False)  # SQLite 資料庫目錄
    db_file: Path = field(init=False)  # SQLite 資料庫檔案路徑
    research_run_db_file: Path = field(init=False)  # Research Run Registry SQLite 檔案
    research_run_parquet_dir: Path = field(init=False)  # Research Run 詳細資料目錄
    research_run_staging_dir: Path = field(init=False)  # Research Run 暫存目錄
    use_sqlite: bool = True  # 是否使用 SQLite 儲存

    # 個人儲存候選為 data_root / "personal"，仍須成對明示；不自動配置、建立或遷移。
    personal_data_root: Path | None = field(
        default_factory=lambda: _optional_env_path("PERSONAL_DATA_ROOT"), kw_only=True,
    )
    personal_watchlist_source: Path | None = field(
        default_factory=lambda: _optional_env_path("PERSONAL_WATCHLIST_SOURCE"), kw_only=True,
    )
    # notes 選擇獨立於 watchlist；root 與模式須成對明示，沒有自動 migration。
    personal_journal_root: Path | None = field(
        default_factory=lambda: _optional_env_path("PERSONAL_JOURNAL_ROOT"), kw_only=True,
    )
    personal_journal_mode: str | None = field(
        default_factory=lambda: os.environ.get("PERSONAL_JOURNAL_MODE", "").strip() or None,
        kw_only=True,
    )
    # Portfolio／Review 的獨立 opt-in，不依 watchlist activation 或 notes 切換。
    personal_store_root: Path | None = field(
        default_factory=lambda: _optional_env_path("PERSONAL_STORE_ROOT"), kw_only=True,
    )
    personal_store_mode: str | None = field(
        default_factory=lambda: os.environ.get("PERSONAL_STORE_MODE", "").strip() or None,
        kw_only=True,
    )

    # UI 與每日個人推論共用已保存 policy；指定路徑不會建立或啟用模型。
    personal_model_policy_path: Path | None = field(
        default_factory=lambda: _optional_env_path("PERSONAL_MODEL_POLICY_PATH"),
        kw_only=True,
    )
    # 官方日曆為外部唯讀證據；Python 與 exe 沿共同設定選同一保存根。
    official_calendar_cache_path: Path | None = field(
        default_factory=lambda: _optional_env_path("OFFICIAL_CALENDAR_CACHE_PATH"),
        kw_only=True,
    )
    # 外部已保存完整母體來源只供瀏覽；不建立來源目錄或擴大 producer 寫入範圍。
    technical_universe_read_root: Path | None = field(
        default_factory=_technical_universe_read_root_from_environment,
        kw_only=True,
    )
    # 基本面唯讀操作先複製到明示隔離根；未設定時不得選用正式輸出或QA預設根。
    fundamental_read_snapshot_root: Path | None = field(
        default_factory=_fundamental_read_snapshot_root_from_environment,
        kw_only=True,
    )
    # H20 封存 SQLite 的 operation-local 唯讀副本根；僅讀既有設定，不建立目錄。
    personal_h20_sqlite_read_root: Path | None = field(
        default_factory=_personal_h20_sqlite_read_root_from_environment,
        kw_only=True,
    )

    # PIT sector membership 是 opt-in 的唯讀輸入；未設定時不做目錄掃描。
    pit_sector_membership_path: Path | None = field(
        default_factory=lambda: _optional_env_path("PIT_SECTOR_MEMBERSHIP_PATH"),
        kw_only=True,
    )
    pit_sector_membership_raw_root: Path | None = field(
        default_factory=lambda: _optional_env_path("PIT_SECTOR_MEMBERSHIP_RAW_ROOT"),
        kw_only=True,
    )
    pit_sector_membership_clock_manifest_path: Path | None = field(
        default_factory=lambda: _optional_env_path("PIT_SECTOR_MEMBERSHIP_CLOCK_MANIFEST_PATH"),
        kw_only=True,
    )
    pit_sector_membership_universe_symbols_path: Path | None = field(
        default_factory=lambda: _optional_env_path("PIT_SECTOR_MEMBERSHIP_UNIVERSE_SYMBOLS_PATH"),
        kw_only=True,
    )
    pit_sector_membership_universe_identity_path: Path | None = field(
        default_factory=lambda: _optional_env_path("PIT_SECTOR_MEMBERSHIP_UNIVERSE_IDENTITY_PATH"),
        kw_only=True,
    )
    pit_sector_membership_taxonomy_identity_path: Path | None = field(
        default_factory=lambda: _optional_env_path("PIT_SECTOR_MEMBERSHIP_TAXONOMY_IDENTITY_PATH"),
        kw_only=True,
    )
    pit_membership_expected_classification_version: str | None = field(
        default_factory=lambda: os.environ.get("PIT_MEMBERSHIP_EXPECTED_CLASSIFICATION_VERSION") or None,
        kw_only=True,
    )
    pit_market_scope: str | None = field(
        default_factory=lambda: os.environ.get("PIT_MARKET_SCOPE") or None,
        kw_only=True,
    )

    # 技術指標 process-pool（預設關閉；只有受控 caller 明確開啟才會使用）
    # worker 僅回傳計算結果，CSV／SQLite 一律由父程序單一寫入者處理。
    technical_process_pool_enabled: bool = field(default=False, kw_only=True)
    technical_process_pool_workers: int = field(default=2, kw_only=True)
    technical_process_pool_max_in_flight: int = field(default=4, kw_only=True)
    technical_process_pool_max_retries: int = field(default=1, kw_only=True)
    
    # 關鍵檔案路徑
    market_index_file: Path = field(init=False)
    industry_index_file: Path = field(init=False)
    stock_data_file: Path = field(init=False)
    all_stocks_data_file: Path = field(init=False)  # 新增整合性數據文件
    broker_flow_dir: Path = field(init=False)  # 券商分點資料目錄
    broker_branch_registry_file: Path = field(init=False)  # 分點 registry 檔案
    monthly_revenue_availability_file: Path = field(init=False)
    statement_availability_file: Path = field(init=False)
    
    # 數據參數
    default_start_date: str = "2014-01-01"
    backup_keep_days: int = 7
    backup_keep_dates: int = 5
    min_data_days: int = 30
    
    # API請求配置
    request_timeout: int = 30
    max_retries: int = 3
    retry_delay: int = 5
    
    def __post_init__(self):
        """初始化衍生屬性"""
        if self.technical_universe_read_root is not None:
            technical_root = Path(self.technical_universe_read_root).expanduser()
            if not technical_root.is_absolute():
                raise ValueError("TECHNICAL_UNIVERSE_READ_ROOT 必須是明示絕對路徑")
            self.technical_universe_read_root = technical_root.resolve(strict=False)
        if self.fundamental_read_snapshot_root is not None:
            snapshot_root = Path(self.fundamental_read_snapshot_root).expanduser()
            if not snapshot_root.is_absolute():
                raise ValueError("FUNDAMENTAL_READ_SNAPSHOT_ROOT 必須是明示絕對路徑")
            # 不在設定解析時建立或resolve來源：操作入口會拒絕reparse與資料根重疊。
            self.fundamental_read_snapshot_root = snapshot_root
        if self.personal_h20_sqlite_read_root is not None:
            h20_read_root = Path(self.personal_h20_sqlite_read_root).expanduser()
            if not h20_read_root.is_absolute():
                raise ValueError("PERSONAL_H20_SQLITE_READ_ROOT 必須是明示絕對路徑")
            # 來源隔離與檔案系統安全由實際 pinned source session 驗證；設定層不推測親緣。
            self.personal_h20_sqlite_read_root = h20_read_root
        if self.personal_model_policy_path is not None:
            requested_policy = Path(self.personal_model_policy_path).expanduser()
            if not requested_policy.is_absolute():
                raise ValueError("personal_model_policy_path 必須是明示絕對路徑")
            self.personal_model_policy_path = requested_policy
        # 處理路徑覆蓋邏輯
        self._resolve_paths()
        self._validate_personal_storage_selection()
        from app_module.personal_journal_paths import resolve_journal_storage_selection
        notes = resolve_journal_storage_selection(self)
        if notes.paths is not None:
            self.personal_journal_root = notes.paths.personal_paths.personal_root
        
        # 設定數據目錄
        self.data_dir = self.data_root
        self.daily_price_dir = self.data_dir / 'daily_price'
        self.tpex_daily_price_dir = self.data_dir / 'daily_price_tpex'
        self.meta_data_dir = self.data_dir / 'meta_data'
        self.technical_dir = self.data_dir / 'technical_analysis'
        self.log_dir = self.output_root / 'application_state' / 'logs'
        self.sqlite_dir = self.data_dir / 'sqlite'
        self.db_file = self.sqlite_dir / 'twstock.db'
        from app_module.personal_store_selection import resolve_personal_store_selection
        stores = resolve_personal_store_selection(self)
        if stores.paths is not None:
            self.personal_store_root = stores.paths.personal_root
        research_run_dir = self.output_root / 'research_runs'
        self.research_run_db_file = research_run_dir / 'research_runs.db'
        self.research_run_parquet_dir = research_run_dir / 'parquet'
        self.research_run_staging_dir = research_run_dir / 'staging'
        
        # 設定關鍵檔案路徑
        self.market_index_file = self.meta_data_dir / 'market_index.csv'
        self.industry_index_file = self.meta_data_dir / 'industry_index.csv'
        self.stock_data_file = self.meta_data_dir / 'stock_data_whole.csv'
        self.all_stocks_data_file = self.meta_data_dir / 'all_stocks_data.csv'
        self.broker_flow_dir = self.data_dir / 'broker_flow'
        self.broker_branch_registry_file = self.meta_data_dir / 'broker_branch_registry.csv'
        self.monthly_revenue_availability_file = self.meta_data_dir / 'monthly_revenue_availability.csv'
        self.statement_availability_file = self.meta_data_dir / 'fundamental_statement_availability.csv'
        
        # 確保所需目錄存在
        self._ensure_directories()
        
        # 創建備份目錄
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # 設置日誌
        self._setup_logging()
        
        # 記錄最終解析的路徑
        self.logger.info(f"數據根目錄: {self.data_root}")
        self.logger.info(f"輸出根目錄: {self.output_root}")
        self.logger.info(f"配置檔案: {self.profile}")
    
    def _validate_personal_storage_selection(self) -> None:
        if self.personal_data_root is None and self.personal_watchlist_source is None:
            return
        if self.personal_data_root is None or self.personal_watchlist_source is None:
            raise ValueError("personal_storage_selection_incomplete")
        from app_module.personal_data_paths import resolve_personal_data_paths
        paths = resolve_personal_data_paths(
            self.data_root, personal_root=self.personal_data_root,
            legacy_output_root=self.output_root, environ={},
        )
        package_root = Path(__file__).resolve().parents[1]
        if paths.personal_root == package_root or paths.personal_root.is_relative_to(package_root) or package_root.is_relative_to(paths.personal_root):
            raise ValueError("personal_root_overlaps_application_package")
        self.personal_data_root = paths.personal_root
        source = Path(self.personal_watchlist_source).expanduser()
        if not source.is_absolute():
            raise ValueError("personal_watchlist_source_absolute_required")
        self.personal_watchlist_source = source

    def _resolve_paths(self):
        """解析路徑覆蓋邏輯"""
        # 確保路徑是Path對象
        if isinstance(self.data_root, str):
            self.data_root = Path(self.data_root)
        if isinstance(self.output_root, str):
            self.output_root = Path(self.output_root)
            
        # 如果是測試環境，自動添加_test後綴
        if self.profile == "test":
            self.data_root = self.data_root / "_test"
            self.output_root = self.output_root / "_test"
            
        # 保持向後兼容
        self.base_dir = self.data_root
        
        # 輸出基礎路徑信息（使用 logger 避免編碼和 I/O 問題）
        try:
            logger = logging.getLogger(__name__)
            logger.info(f"數據目錄設置為: {self.data_root}")
            logger.info(f"輸出目錄設置為: {self.output_root}")
            logger.info(f"配置檔案: {self.profile}")
        except (UnicodeEncodeError, ValueError, OSError) as e:
            # 如果遇到編碼或 I/O 問題（例如標準輸出已關閉），使用 logger 或靜默處理
            try:
                logger = logging.getLogger(__name__)
                logger.debug(f"Data directory: {self.data_root}")
                logger.debug(f"Output directory: {self.output_root}")
                logger.debug(f"Profile: {self.profile}")
            except:
                # 如果連 logger 都失敗，靜默處理（避免在動態導入時崩潰）
                pass
    
    def resolve_path(self, subfolder: str) -> Path:
        """解析子資料夾路徑並創建目錄"""
        path = self.data_root / subfolder
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    def resolve_output_path(self, subfolder: str) -> Path:
        """解析輸出子資料夾路徑並創建目錄"""
        path = self.output_root / subfolder
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    def _ensure_directories(self):
        """確保所需目錄結構存在"""
        directories = [
            self.output_root,
            self.daily_price_dir,
            self.tpex_daily_price_dir,
            self.meta_data_dir,
            self.technical_dir,
            self.backup_dir,
            self.log_dir,  # 應用程式執行日誌位於輸出根目錄
            self.sqlite_dir,  # SQLite 資料庫目錄
            self.research_run_db_file.parent,
            self.research_run_parquet_dir,
            self.research_run_staging_dir,
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    @property
    def backup_dir(self) -> Path:
        """備份目錄路徑"""
        return self.meta_data_dir / 'backup'
    
    def get_technical_file(self, stock_id: str) -> Path:
        """取得特定股票的技術分析檔案路徑"""
        return self.technical_dir / f'{stock_id}_indicators.csv'
    
    def get_daily_price_file(self, date: str) -> Path:
        """取得特定日期的價格檔案路徑
        
        Args:
            date: 日期字串，格式為 YYYY-MM-DD 或 YYYYMMDD
        """
        # 轉換日期格式為 YYYYMMDD
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date):
            # YYYY-MM-DD 格式，轉換為 YYYYMMDD
            date_obj = datetime.strptime(date, '%Y-%m-%d')
            date_str = date_obj.strftime('%Y%m%d')
        elif re.match(r'^\d{8}$', date):
            # 已經是 YYYYMMDD 格式
            date_str = date
        else:
            # 其他格式，嘗試解析
            try:
                date_obj = datetime.strptime(date, '%Y-%m-%d')
                date_str = date_obj.strftime('%Y%m%d')
            except:
                date_str = date.replace('-', '')  # 簡單移除連字符
        
        return self.daily_price_dir / f'{date_str}.csv'
    
    def _backup_prefix_from_name(self, backup_file: Path, fallback_prefix: str) -> str:
        """從備份檔名推導清理前綴，讓顯式備份檔名也能共用清理規則。"""
        match = re.match(r"^(?P<prefix>.+)_\d{8}(?:_\d{6})?$", backup_file.stem)
        if match:
            return match.group("prefix")
        return fallback_prefix

    def _backup_sort_key(self, backup_file: Path, file_prefix: str | None = None) -> tuple[str, str]:
        """解析備份檔名中的日期與時間；無法解析時回傳空值以避免誤刪。"""
        if file_prefix is None:
            pattern = r"^.+_(?P<date>\d{8})(?:_(?P<time>\d{6}))?$"
        else:
            pattern = rf"^{re.escape(file_prefix)}_(?P<date>\d{{8}})(?:_(?P<time>\d{{6}}))?$"
        match = re.match(pattern, backup_file.stem)
        if not match:
            return ("", "")
        return (match.group("date"), match.group("time") or "")

    def _cleanup_old_backups(self, file_prefix: str):
        """清理備份檔：同一來源同一天只留最新一份，且最多保留五個日期版本。"""
        backups_by_date: dict[str, list[Path]] = {}
        for backup_file in self.backup_dir.glob(f"{file_prefix}_*"):
            try:
                date_key, _ = self._backup_sort_key(backup_file, file_prefix)
                if not date_key:
                    continue
                backups_by_date.setdefault(date_key, []).append(backup_file)
            except Exception:
                continue

        for date_key, backup_files in backups_by_date.items():
            sorted_files = sorted(
                backup_files,
                key=lambda path: (self._backup_sort_key(path, file_prefix), path.stat().st_mtime),
                reverse=True,
            )
            for backup_file in sorted_files[1:]:
                try:
                    backup_file.unlink()
                except Exception:
                    continue

        keep_dates = sorted(backups_by_date.keys(), reverse=True)[: self.backup_keep_dates]
        for date_key, backup_files in backups_by_date.items():
            if date_key in keep_dates:
                continue
            for backup_file in backup_files:
                try:
                    if backup_file.exists():
                        backup_file.unlink()
                except Exception:
                    continue
    
    def _setup_logging(self):
        """設置日誌"""
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        # 避免重複添加處理器，導致 I/O on closed file
        if not self.logger.handlers:
            # 控制台處理器永遠保留；read-only CLI 不應因 log 目錄不可寫而無法啟動。
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            
            # 設置格式
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

            # 創建文件處理器；正式環境可寫時保留持久化 log，唯讀或受限環境則降級。
            try:
                file_handler = logging.FileHandler(
                    self.log_dir / "config.log",
                    encoding='utf-8'
                )
            except (OSError, ValueError) as exc:
                self.logger.warning(
                    "無法建立配置檔案日誌，改用 console-only: %s",
                    exc,
                )
            else:
                file_handler.setLevel(logging.INFO)
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)
    
    def create_backup(self, source_file: Path, backup_file: Path = None):
        """創建文件備份"""
        try:
            if not source_file.exists():
                return
                
            if backup_file is None:
                # 使用時間戳創建備份文件名
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_file = self.backup_dir / f"{source_file.stem}_{timestamp}{source_file.suffix}"
            
            # 創建備份
            shutil.copy2(source_file, backup_file)
            self.logger.info(f"已創建備份文件: {backup_file}")
            
            # 清理舊備份
            cleanup_prefix = self._backup_prefix_from_name(backup_file, source_file.stem)
            self._cleanup_old_backups(cleanup_prefix)
            return backup_file
            
        except Exception as e:
            self.logger.error(f"創建備份時發生錯誤: {str(e)}")
    
    def restore_backup(self, backup_file: Path, target_file: Path):
        """從備份文件恢復"""
        try:
            if not backup_file.exists():
                self.logger.error(f"備份文件不存在: {backup_file}")
                return False
                
            shutil.copy2(backup_file, target_file)
            self.logger.info(f"已從備份文件 {backup_file} 恢復到 {target_file}")
            return True
            
        except Exception as e:
            self.logger.error(f"恢復備份時發生錯誤: {str(e)}")
            return False

    @classmethod
    def from_args(cls, args=None):
        """從命令行參數創建配置實例"""
        if args is None:
            args = sys.argv[1:]
            
        parser = argparse.ArgumentParser(description='baldr 配置')
        parser.add_argument("--data-root", type=str, help="覆蓋數據根目錄路徑")
        parser.add_argument("--output-root", type=str, help="覆蓋輸出根目錄路徑")
        parser.add_argument("--personal-data-root", type=Path, help="個人儲存候選root；須與來源成對，不自動啟用")
        parser.add_argument("--personal-watchlist-source", type=Path, help="明示既有JSON／SQLite來源；只讀保留")
        parser.add_argument("--personal-journal-root", type=Path, help="明示 notes 個人root；須搭配模式")
        parser.add_argument("--personal-journal-mode", choices=["personal", "legacy_read_only"],
                            help="notes 個人寫入或固定舊來源唯讀；不搬移資料")
        parser.add_argument("--personal-store-root", type=Path, help="明示 Portfolio／Review 私人root；須搭配模式")
        parser.add_argument("--personal-store-mode", choices=["personal", "legacy_read_only"],
                            help="私人 store 或固定舊來源唯讀；不搬移、不啟用 watchlist")
        parser.add_argument("--profile", type=str, default="prod", 
                           choices=["prod", "staging", "test"], help="配置檔案")
        parser.add_argument("--dry-run", action="store_true", help="乾運行模式，不實際寫入檔案")
        
        parsed_args = parser.parse_args(args)
        
        # 創建配置實例，優先使用命令行參數
        config_kwargs = {}
        if parsed_args.data_root:
            config_kwargs['data_root'] = Path(parsed_args.data_root)
        if parsed_args.output_root:
            config_kwargs['output_root'] = Path(parsed_args.output_root)
        if parsed_args.personal_data_root is not None:
            config_kwargs['personal_data_root'] = parsed_args.personal_data_root
        if parsed_args.personal_watchlist_source is not None:
            config_kwargs['personal_watchlist_source'] = parsed_args.personal_watchlist_source
        if parsed_args.personal_journal_root is not None:
            config_kwargs['personal_journal_root'] = parsed_args.personal_journal_root
        if parsed_args.personal_journal_mode is not None:
            config_kwargs['personal_journal_mode'] = parsed_args.personal_journal_mode
        if parsed_args.personal_store_root is not None:
            config_kwargs['personal_store_root'] = parsed_args.personal_store_root
        if parsed_args.personal_store_mode is not None:
            config_kwargs['personal_store_mode'] = parsed_args.personal_store_mode
        if parsed_args.profile:
            config_kwargs['profile'] = parsed_args.profile
            
        return cls(**config_kwargs), parsed_args
