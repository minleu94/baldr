# BALDR B08 私人路由契約 QA

## 範圍與狀態

B08 新增純型別的私人 store 路由契約，供後續 caller 選擇既有 repository 的讀取來源與寫入目標。這項工作尚未接到 Portfolio、Paper、Quality、Journal 或 Evidence caller；不代表這些 caller 已完成私人資料隔離，也沒有啟用私人資料庫、搬移資料或建立 schema。

`select_personal_store_route(...)` 僅組合 `Path`，不檢查檔案、開啟資料庫、建立目錄或搬移／複製資料。選取 PERSONAL 路由時，私人路徑即為 read source 和 write target；路徑不存在表示私人 store 目前為空，caller 不得改讀 legacy 資料。未設定私人選擇時，caller 應明確選 `LEGACY_COMPAT` 以保留既有路徑；明確的 `LEGACY_READ_ONLY` 路由沒有 writer。

API 位於 `app_module/personal_store_routes.py`：

```python
select_personal_store_route(
    *,
    domain: PersonalStoreDomain,
    mode: PersonalStoreMode,
    identity: StoreIdentity | None,
    personal_paths: PersonalDataPaths | None = None,
    legacy_output_root: Path | None = None,
    market_db_path: Path | None = None,
    portfolio_ledger_path: Path | None = None,
    evidence_refs: tuple[EvidenceSourceRef, ...] = (),
) -> PersonalStoreRoute
```

每項路由都要求 caller 提供已解析的 `StoreIdentity`；身分未知時以該 domain 命名的錯誤拒絕。路由選擇不取代既有 canonical/link/reparse/hardlink 驗證；caller 在任何檔案 I/O 前仍須透過現有 personal path guard 驗證，並在 I/O 邊界使用 `personal_data_paths.py` 的 renderer。

## Domain 路徑

| Domain | PERSONAL read/write | LEGACY_COMPAT read/write | LEGACY_READ_ONLY | 路由限制 |
|---|---|---|---|---|
| Trades | `<personal_root>/portfolio/trades.jsonl` | `<legacy_output_root>/portfolio/trades.jsonl` | 同 legacy 路徑，只讀 | 相容 `PortfolioJsonlStore` 的 trades 子路徑；selector 不建目錄或 store。 |
| Declared holdings | `<personal_root>/portfolio/user_declared_holdings.jsonl` | `<legacy_output_root>/portfolio/user_declared_holdings.jsonl` | 同 legacy 路徑，只讀 | 對應 `UserDeclaredHoldingResearchStore` 的既有 JSONL 路徑。 |
| Paper | `<personal_root>/paper_portfolio/paper_trade_ledger.sqlite` | `<legacy_output_root>/paper_portfolio/paper_trade_ledger.sqlite` | 同 legacy 路徑，只讀 | 對應既有 Paper trade ledger；與 generic Portfolio ledger 分開。其他 Paper state／EOD replay 路徑不由此契約重新分類。 |
| Portfolio ledger | caller 明確提供且位於 `<personal_root>` 下的 `portfolio_ledger_path` | caller 明確提供既有 `portfolio_ledger_path` | 同 caller 路徑，只讀 | 既有 `PortfolioLedgerRepository` 接受明確 `db_path`，但沒有本契約可確認的預設檔名；缺路徑或身分即具名拒絕，不猜 store。 |
| Review | `<personal_root>/reviews/decision_quality.sqlite` | 明確 `market_db_path`，維持既有 Quality DB 路徑 | 同市場 DB 路徑，只讀 | PERSONAL writer 和 reader 都落在私人 Review DB；legacy 相容路由標記為 legacy。Review 可額外保留原樣 `EvidenceSourceRef(source_db, event_id)`。 |
| Evidence | 不適用 | 不適用 | 僅 `MARKET_READ_ONLY`：明確 `market_db_path` | `write_target=None`；混合 lineage 只保留來源引用，不複製市場 DB。 |

資料表／repository 對照：Paper trade ledger 使用既有 `paper_trade_ledger` schema；generic Portfolio ledger 使用 `portfolio_ledger_events`；Decision Quality Review 使用既有 `DecisionQualityRepository` 表；Evidence repository 的來源資料位於市場 DB（含 `evidence_events`／`evidence_outcomes`）。契約不建立或改寫任何 schema。

未設定 `PERSONAL_DATA_ROOT` 或個人 selector 的 legacy caller 行為須由後續 caller 明確映射至 `LEGACY_COMPAT`。選擇器不讀取全域設定，也不自行推斷 mode。個人模式不會以空私人 store 作 legacy fallback。Evidence 只接受 `MARKET_READ_ONLY`；其他 domain 不可選此 mode。Portfolio ledger PERSONAL 路徑若包含 `..` 或不在 personal root 下會拒絕。

## 驗證

- `python -m pytest tests/test_personal_store_routes.py -q -o addopts=`：21 passed。pytest 回報 `.pytest_cache` nodeids 寫入權限警告；測試本身全數通過。
- `python -m mypy app_module/personal_store_routes.py`：通過，1 source file。
- `python -m py_compile app_module/personal_store_routes.py tests/test_personal_store_routes.py`：通過。
- 測試使用 `tmp_path` 合成路徑；沒有讀寫真實資料庫。涵蓋個人空路徑不 fallback、legacy 讀寫／唯讀分流、mode 限制、身份與設定缺失、Ledger 明確路徑／越界拒絕、Paper 與 Portfolio ledger 路徑分離、Review 來源引用保留，以及 selector 不建立 personal root。

## 回復與未驗證範圍

回復 B08 本身時，可移除新增的 `app_module/personal_store_routes.py`、`tests/test_personal_store_routes.py` 與本 QA 文件。`app_module/personal_data_paths.py` 的 Windows I/O helper 是獨立且已由 parent review/commit 的 B02 依賴，不屬於此回復範圍。

B09/B10 尚未接線，既有 Journal/Quality/Evidence caller 的實際讀寫行為沒有由本輪路由測試覆蓋；沒有執行資料庫遷移、實際 DB read/write、啟用或 rollback。正式 caller 尚須整合 mode 選擇、逐路徑 canonical/link/hardlink guard，並各自驗證 repository schema 與 writer 行為。
