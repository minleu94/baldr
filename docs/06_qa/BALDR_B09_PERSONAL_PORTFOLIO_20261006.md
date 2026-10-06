# B09 Portfolio／Paper 私人路由 backend 交接

日期：2026-10-06。狀態：typed backend／consumer 隔離驗證完成，待中央 caller 接線與整合。不是正式 Paper producer 切換、migration 或產品資格完成。

## 基準與範圍

- 固定 base：`ba4e9e59da7946aa66fd5eac3729e091dfe5cced`。
- branch：`lane/baldr-b09-personal-portfolio-20261006`；worktree：`output/worktrees/baldr-b09-personal-portfolio`。
- B08 定版依賴：`fdb3fc6282638f3e80a3cbfd82bb0c4f7dfe61bb`，本 lane 採入為 `449165bcc`。中央已有 B08 時只採 B09 owned commit。
- ownership：七個指定 backend、新 `personal_paper_store_paths.py`（中央另授權）、專屬測試與本 QA。未改 main/config、B08 route、shared DTO/codec、Manual、原 plan、PortfolioView 或 B10。
- 本 lane 無 sub-agent、dev cherry-pick、push、正式資料讀寫、migration、正式 Task、ACL、清理、Native、訓練或交易。

## API 與拒絕條件

| 入口 | 明示注入與行為 |
|---|---|
| `PortfolioService(config, *, route=None, ledger_route=None, ledger_source_namespace=None)` | `route` 為 TRADES。config 任一 `personal_store_root/mode` 有值卻無 route，在 legacy store constructor 前回 `personal_store_selector_required`。ledger route 必須 PORTFOLIO_LEDGER、identity/mode/source_kind 與 trades 相同、明示 namespace；不能同時注入舊 repository。 |
| `PortfolioJsonlStore(output_root, *, route=None)` | route 存在時只使用 `read_source`；不初始化 legacy 目錄。空檔返回空、不借 legacy。所有交易寫入、讀回與 batch 驗 portfolio_id；route 不提供 journal 存取。readonly 在 mkdir/lock/writer 前拒絕。 |
| `UserDeclaredHoldingResearchStore.from_route(route)` | 僅 DECLARED_HOLDINGS。existing store 注入 `UserDeclaredHoldingResearchService(store, *, config=None)`；config 有私人設定而 store 未 bound 時拒絕。read／revision 驗 exact portfolio_id；readonly 不建 lock，create/revise/archive 在冪等判定前拒絕 writer。 |
| `PortfolioLedgerRepository(path, *, portfolio_id=None, source_namespace=None, read_only=False)` | 資料層只接受帳戶與 namespace 型別值，不反向 import app route。bound get/append/query 不可跨帳戶或 namespace。原 Decimal／整數分 schema 與 hash／compensation 公式不變。 |
| `PersonalPaperStorePaths.from_route(route, *, portfolio_id)` | frozen typed paths，只接受 PAPER 與 exact identity。依既有 layout 映射 state、benchmark、cost、baseline、status；不做 I/O。 |
| `PaperPortfolioReadinessService`／`PaperPortfolioWeeklyEvidenceService` | 新 keyword-only `route=None, config=None`。config 明示卻缺 route 時在 env／舊路徑處理前拒絕；route 的 `portfolio_id` 必須 exact。路徑 override 必須等於 selected path；明示 route 時不採 env override，沒有 status fallback。 |
| `PaperPortfolioSnapshotRepository(db_path, *, route=None, portfolio_id=None)` | routed path 必須等於 Paper state sibling；append/get/list 驗 exact account。readonly 不建立庫／schema，缺庫維持 None／空列；writer 先拒絕。所有連線確實 close。 |

Paper siblings 固定：`paper_portfolio/paper_portfolio.sqlite`、`paper_equal_weight_benchmark.sqlite`、`paper_trade_ledger.sqlite`、`baseline_20260712.json`，及同 selected root 下 `scheduled/paper_portfolio_daily/latest_status.json`。成本 route 本身不是 state 路徑，不能直接傳給 snapshot repository。

無 route／無私人 config 的既有 API 維持原相容行為。只接受 caller 已解析的 portfolio_id；不能從未知 identity 猜 `default` 或把 Paper／聲明映成真實持倉。只有 root/store 的舊 constructor 看不到全域 config；中央必須在 service 邊界傳入 `config` 與已選 route。readonly 不保證同時有外部 writer 時的 JSONL snapshot 一致性；本輪 synthetic 驗證在無並行 writer 下進行。

## 中央接線提案（只讀建議，未修改）

中央 `resolve_personal_store_selection(config)` 應先完成 pair／identity 選擇，之後組成以下 caller；變數皆必須來自已解析 selector，不能新造 default。

```python
portfolio_service = PortfolioService(config, route=trades_route)
declared_service = UserDeclaredHoldingResearchService(
    UserDeclaredHoldingResearchStore.from_route(declared_route), config=config,
)
paper_readiness = PaperPortfolioReadinessService(
    output_root=config.output_root, route=paper_route, config=config,
    portfolio_id=paper_route.identity.key,
)
paper_weekly = PaperPortfolioWeeklyEvidenceService(
    output_root=config.output_root, route=paper_route, config=config,
    portfolio_id=paper_route.identity.key,
)
```

- `ui_qt/main.py` base 358：將 PortfolioService 注入 exact trades route；base 427–429 的 Journey `portfolio_trades_path` 使用 `trades_route.read_source`。
- `PortfolioView` base 1010／1027／1030：由中央／B06 注入 declared、Paper readiness、weekly services，避免 view 自建 legacy stores。非 `default` 帳戶須在 caller 明示 exact portfolio_id；backend 不替 UI 猜身份。
- 精確 ledger 仍 opt-in：只有中央已解析 `portfolio_ledger_path`、portfolio_id、namespace 才給 `ledger_route`＋`ledger_source_namespace`；未選 ledger 不偷偷啟用。
- `paper_trade_ledger.py`、benchmark／baseline／daily producer 未屬 B09 writer ownership，維持原鏈。這次只完成指定 snapshot writer 與 typed consumers；完整 Paper producer 路由需中央另鎖 scope，不能稱正式鏈 complete。
- Manual／Snapshot／architecture／routing 的實際 caller 狀態由唯一中央 owner 同步；原 plan 只讀，本 QA 不提升 UX、PIT、自然樣本或 Formal credit。

## 驗證與來源保存

執行 interpreter：repo 共用 `C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe`；cwd 為 B09 worktree。fixture 僅 pytest 的授權使用者 Temp。原始資料與正式根完全未使用。

1. 最終 focused union：**100 passed，4.61s**。命令：

```powershell
python -m pytest tests/test_baldr_b09_personal_portfolio.py tests/test_portfolio_jsonl_store_serialization.py tests/test_user_declared_holding_research.py tests/test_paper_portfolio_readiness_service.py tests/test_paper_portfolio_snapshot_repository.py tests/test_paper_portfolio_weekly_evidence_service.py tests/test_portfolio_mvp.py tests/test_portfolio_delete.py tests/test_portfolio_numeric_governance.py tests/test_formal_portfolio_ledger.py tests/test_personal_store_routes.py -q -o addopts=
```

2. targeted mypy：八個 changed source modules 通過；changed Python compile：八 source＋一測試通過。
3. `scripts/quant_guard_linter.py`：float boundary／look-ahead AST 均通過；`git diff --check` 通過。
4. 新專屬測試含三組 config 缺 route guard；空 personal／legacy readonly；錯 domain、account、namespace；Paper status／env override；合成 JSONL 精度、declared identity、ledger、Paper snapshot 新 process exact readback；create-only fixture copy／恢復後再讀；Paper state／benchmark／cost 新 process 同源 consumer。各步都比對來源 SHA-256 不變，legacy hash 不變。
5. 第一次新測試 7 pass／1 fail 是 ledger fixture 未固定 created_at，repository 合法補入保存時鐘；固定合成 created_at 後保留完整 equality 檢查通過。後續增加獨立 Paper consumer 與 config guard；不將累積跑次相加為分母。

本輪新增路徑／身份約束，不修改 signal、cutoff、行情、標準化、停損停利、成本、fill 或 benchmark 公式。聲明 read_heads_as_of 原 created_at cutoff、Paper future-date／period gate 及 availability 限制保留；synthetic fixtures 只驗工程序列化，不補造資料資格。金融值使用 Decimal／既有整數欄位，無新增 float 計算。

raw logs 保留在本 worktree `output/qa/baldr_b09_20261006/`，不提交：

| log | SHA-256 |
|---|---|
| final_union.log | `dc7197154864b3b8ac28712a2b9f73896e5296411e01411dfbf4bb7b17e9884d` |
| final_mypy.log | 同內容 targeted success，hash 隨 handoff manifest 交中央 |
| final_quant.log | 同內容 quant pass，hash 隨 handoff manifest 交中央 |

重型 Workbench／validator／完整 mypy／Native 未在本 lane 重跑；中央穩定 union 接線後排一次。沒有以 sourcehash 不變冒稱正式資料測試。

## 回滾清單

| 檔案 | 類型 | 回滾方式 | 風險 |
|---|---|---|---|
| portfolio_service.py／portfolio_store.py／user_declared_holding_research.py | 修改 | 在確認 caller 狀態後 revert B09 owned commit | 撤回明示私人 route／readonly guard；需同步撤回 caller 注入 |
| paper_portfolio_readiness_service.py／paper_portfolio_snapshot_repository.py／paper_portfolio_weekly_evidence_service.py | 修改 | 同上 | 撤回 Paper paths consumer／readonly snapshot；不回滾資料 |
| data_module/portfolio_ledger_repository.py | 修改 | 同上 | 撤回 bound account／namespace；原 schema 不受影響 |
| app_module/personal_paper_store_paths.py／tests/test_baldr_b09_personal_portfolio.py／本 QA | 新增 | 同一 owned commit revert | 中央先確認無 caller 依賴；無正式資料風險 |

回滾步驟：先 `git status --short` 確認不含別人 dirty；中央檢查所有新 API caller；在整合分支以 `git revert <B09完整commit>` 撤回，focused 驗回原相容入口。B08 定版與原始 fixture／資料不隨 B09 回滾刪除。此清單是可執行提案，未執行清理或回滾。

待中央：採 owned commit、main/config／B06 caller／B10 bound service 接線、Manual 同步與一次穩定 union gates。backend 完成不代表 Paper producer、真 migration、真人／Native、投資有效性或自然時間 gate 完成。
