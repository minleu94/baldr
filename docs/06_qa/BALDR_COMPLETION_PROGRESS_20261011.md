# Baldr 補完接續（2026-10-11，進行中）

完整需求仍依 [原補完計畫](../superpowers/plans/baldr_product_completion_plan_20261006.md)，保留 P00–P14、M1–M3、F01–F23 與 G0–G4。本文只記錄本次實作與驗證，不取代 Snapshot 或 Manual。起點為 `dev`／`04b35387`；原九份文件 dirty 保留。

## 排他分工

| Owner | 可寫範圍 | 出口 |
|---|---|---|
| p01_perf（Luna Max） | `personal_data_paths.py`、其測試與隔離 QA | 先取 current-source 真 API profile，再依證據改善；原 300ms 不變 |
| f12_journey（Luna Max） | 新營收 Main 旅程測試與隔離 QA | 精確只讀 SQL 角色、真確認／收藏／關閉／新程序重開 |
| p08_daily（Luna Max） | 新 `strategy_paper_account_daily.py`／測試；既有 `paper_trade_ledger.py`／測試 | 同交易 CAS、有序 fills、零成交與跨 DB 重試；正式 quote clock 缺口保留 |
| root | 配置 DTO／service、新持倉情境 service／測試、共用 UI／文件 | 純規則入口沿既有金融計算，已選帳本研究情境保存、讀回及 UI |

## Root 實作前檢查

- 量化 guard 已執行，兩項靜態檢查通過；其白名單不等同新情境因果性證明。
- 情境只接受決策前已知的完整帳本狀態與行情；同日／未來狀態不授執行提案；未知持倉不得補零。
- 等權與明示目標沿既有整數 bp／Decimal 引擎。純規則入口不得建立假 model／dataset 身分，也不授 broker 或 rebalance 權限。

## 回滾清單

### 變更檔案清單

| 檔案 | 類型 | 摘要 | 回滾方式 | 風險 |
|---|---|---|---|---|
| `app_module/portfolio_allocation_dtos.py` | 修改 | 新增純規則請求／數值投影契約 | 保存當前差異並核對 owner，只還原本輪 diff／preimage | 移除後新情境入口無法 import |
| `app_module/portfolio_allocation_service.py` | 修改 | 現有計算共用於 Rule/ML 與純規則入口 | 同上；不還原其他 lane 檔案 | 須重驗既有 ML 配置回歸 |
| 新 `app_module/portfolio_research_scenario_service.py` | 新增 | 已選帳本研究情境 | 核對 postimage 和依賴後只移除本新增檔 | consumer 需同步解除 |
| 新 `tests/test_baldr_completion_p06_scenarios.py` | 新增 | 真限制／身份／因果性案例 | 同上，只移除本新增檔 | 移除會失去本輪回歸覆蓋 |
| 本文件 | 新增 | 排他 scope、證據及限制 | 核對 owner 後只移除本新增檔 | 交接證據遺失 |
| `docs/01_architecture/system_architecture.md`／`docs/00_core/PROJECT_SNAPSHOT.md` | 修改 | 新 API 的責任及未完成接線 | 只逆向移除本輪新增段／列，保留其他 writer 增量 | 交接狀態不同步 |

### 回滾步驟

1. 比對當前 diff 與 `output/qa/baldr_completion_20261011/root/preimages/`，保存其他 writer 增量。
2. 僅逆向套用 root 差異；新增檔先核 postimage 及 consumer，禁止整個工作樹 reset。
3. 重驗配置與情境定向案例，不回滾任何市場／私人 DB。

## 驗收狀態

本輪尚未關閉任何完整工作包。單元測試、隔離合成旅程、原來源、同版 EXE、Native 與真人接受需分別登記；daily clock 缺口不能以合成成交補足。

### P06 純規則與情境計算增量

- 新增 `PortfolioRuleAllocationRequestV1`／`PortfolioRuleAllocationResultV1`。原 `project()` 保持 Rule/ML metadata 與 authorization 路徑；`project_rule_only()` 與它共用 `_project_weights()`，不建立 ML 提案或模型身分。
- `PortfolioResearchScenarioService.compare()` 只經 `read_exact(account_kind, portfolio_id, snapshot_id)` 讀一次完整帳本狀態，產生維持、等權及明示目標比較。候選排序固定，等權沿既有 Construction，所有風控與成本沿既有 Allocation。
- 純規則 result 綁實際配置 policy hash；comparison input hash 綁帳本、原來源 hash、aware cutoff、全部 context 事實、候選及目標。Health 未知、晚到資料、同日／未來帳本、跨帳本 context、缺持倉、錯股數／權重及缺候選價格均拒絕；不推定健康或空倉。
- 目前只完成計算 API 與 reader protocol。正常帳本 adapter、情境 artifact 保存／公開讀回、Portfolio／個股 UI、返回／新程序及 G3／G4 **尚未完成**，不得將此項列為 P06 或 M3 完成。

| 驗證 | 結果／範圍 |
|---|---|
| allocation service、新 P06 情境、Construction sandbox、Paper policy 四組定向 pytest | **56 PASS**；新情境 23 項、既有 allocation 20 項、Construction／Policy 13 項。Windows 沙箱對 `Path.resolve(strict=True)` 拒絕，改以核准的 elevated process 在工作區 isolated `pytest03` fixture 執行；未碰正式 DB。 |
| 3 個變更 source 的定向 mypy `--follow-imports=silent` | 通過；不宣稱 full repo mypy |
| 3 個變更 source＋新測試 `py_compile` | 通過 |
| `scripts/quant_guard_linter.py` 修改前／後 | 兩項靜態檢查通過；未納白名單的新檔另以 Decimal／因果性測試檢查 |

首輪 19 PASS／1 fixture PermissionError、次輪 40 PASS／3 failures 是本輪過程。次輪兩項新測試修正既有 diagnostic 名稱與缺少的 test ML proposal `coverage_bp`，沒有放寬產品門檻或刪除 assertion。最終 56 PASS 是同組定向回歸終態，不與前輪數字相加。

成功命令：`.\.venv\Scripts\python.exe -m pytest tests/test_portfolio_allocation_service.py tests/test_baldr_completion_p06_scenarios.py tests/test_portfolio_construction_sandbox.py tests/test_paper_portfolio_policy.py -q -o addopts= --basetemp=output/qa/baldr_completion_20261011/root/pytest03`。

### 接續依賴

1. P06 接完整、受治理的帳本／Health reader adapter；缺原 clock 的帳本不能自行填 availability。
2. 設計情境 artifact 的明示私人保存路由與版本 decoder，再接正常 UI；session store 只是記憶體上下文，不能冒稱持久化。
3. P01 現源單次 cProfile 為 641.909ms（插樁診斷，非 p95）。主要成本是 lstat、bounded reads 與路徑檢查；已釋出 narrow absolute builtin Path 候選，不把單次診斷當原 300ms Gate 通過。
4. P08 CAS 葉片的 11 PASS 是 owner 聚焦結果；root 審查要求 `rowset_hash()` 固定同一 read transaction 並補測。daily companion、UI 與正式 clock 尚待，不先收完整葉片。
