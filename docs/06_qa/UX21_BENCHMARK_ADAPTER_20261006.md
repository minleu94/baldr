# UX21 具名 benchmark 唯讀 adapter 獨立 lane

基準 `8a78eac313f8544eb01657da3510fb15af3c179b`；branch `lane/ux21-benchmark-adapter-20261006`。本包只新增 adapter、對應測試與本收據三檔，供主 owner 明示接線。既有 UI、config、Manual、plan、source、store、outcome 核心均未修改；不整合 dev、不 push。

## 範圍與資格

只讀 caller 明示的既存 SQLite `market_indices`，不讀個人資料、不用個股代替大盤、不自動挑選 benchmark、成本、ML target 或 horizon。repo 的 `data_module/market_data_integrity.py` 已定義 `TAIEX` 名稱；這是可選的現存契約，不代表本包已驗證正式資料的來源口徑或官方 availability。

輸入的 basis、幣別與 availability 是 caller 明示的研究契約。它們必須完整、彼此一致且符合來源可見欄位；來源修訂、原決策列與 exact endpoint 必須核對。缺件為 unknown，已知失配為 rejected，不猜來源口徑或補零成本。caller 宣告與 fixtures 不構成官方 qualification、歷史 PIT 或 ML 資格。

所有 formal／PIT／training／trading／natural 資格保持 false。研究結果不得回灌決策訊號；只准 as-of 以前已可得的 exact endpoint，不借鄰日、最新值或未來價格。無 availability 或未成熟不得輸出假成功。

## 文件覆蓋與 ownership

| 路徑 | 類型 | 責任 |
|---|---|---|
| `app_module/rule_research_benchmark_adapter.py` | 新增 | 有界唯讀 adapter 與研究來源契約 |
| `tests/test_rule_research_benchmark_adapter.py` | 新增 | 隔離 fixtures、拒絕分支與原 core 接線測試 |
| 本文件 | 新增 | API、驗證與接手限制 |

Snapshot／Roadmap／架構／Manual／索引與 shared state 的變更由唯一主 owner 管理。本 lane 的三檔限制優先，不另改共用文件；本包沒有產品入口或使用者可見行為變更。原計畫 `output/plans/baldr_product_experience_plan_20261004.md` 唯讀。`.agents/skills` 不存在，沿 `docs/agents/skills/team.md` 與 `quant_defense_guard.md` 既有權威。既有 graphify 圖譜日期為 9/29、UX21 節點未收錄，已用來源程式補核，不重建大型圖譜。

## 回滾

確認隔離 branch 無其他 owner 改動後，執行 `git revert <本包完整 commit hash>`，再跑對應測試。三檔均為新增；尚未接線時無既有功能風險，接線後須由主 owner 一起處理 dependency。保留 branch／worktree 作 review，不清理。

## API 與接線

入口：`load_explicit_market_benchmark(request, *, cancel_callback=None, observed_at=None) -> ExplicitBenchmarkResult`。

`ExplicitBenchmarkRequest` 必須明示 `database_path`、`source_identity`、`benchmark_name`、`decision_date`、`endpoint_dates`（包含 decision，最多四日）、`as_of_date`、`currency`、`unit`、`price_basis`、`corporate_action_basis`。另有 `availability_by_date`、`target_currency`、`target_price_basis`、`target_corporate_action_basis`、`expected_rowset_sha256`、`expected_decision_row_sha256`；這些欄位可缺省，以 unknown 診斷缺件，不自動補值。

結果為 frozen dataclass，含 `status`、`reason_codes`、`benchmark`、`prices`、`observed_rowset_sha256`、`observed_decision_row_sha256`、`source_contract_json`／`source_contract_sha256`、`observed_at_utc` 與資格旗標。只有 `qualified_research` 才提供 spec／prices；`unknown`／`rejected` 保持空價格。`qualification_scope=caller_declared_research_only` 明示來源宣告的研究界線。

第一次未附預期 hashes 時只回 unknown 與 observed pins；caller 審核來源並固定該 revision／原決策列後，可用同一 request 加上兩個 expected hashes 再讀。這個過程不能替代來源口徑／availability qualification，也不能盲目接受最新 revision。qualified 的 instrument ID 為 `market_indices.<明示名稱>`，source identity 綁同一 contract hash；core 可用 `benchmark=result.benchmark`、`prices=(*target_prices, *result.prices)` 接入。未知結果應保留其原因，不借用其他來源拼合。

rowset pin 表示實際選中來源列的型別化身份，原決策列另有獨立 pin；請求期間／as-of／availability／source 與 target metadata 由 contract hash 綁定。主 owner 保存時必須一併保存 contract，不能把 rowset pin 當成完整比較請求。`observed_at` 是另列的觀測時鐘，不取代來源 availability 或原決策時鐘。

日期支援明確的 `YYYY-MM-DD`、`YYYY/MM/DD`、`YYYYMMDD`，正規化成 ISO；同日 alias 重複拒絕。價格從 SQLite `CAST AS TEXT` 跨入 `Decimal`，避免新裸 float 計算；來源若本身是 REAL，只承諾 SQLite 可讀文字值，不補造原始十進位精度。指數點數與股票股數 unit 可不同，但 currency／price basis／corporate-action basis 必須與 caller 明示 target 相符。未知成本保持原 core 的 net／excess 契約，不在 adapter 配置。

## 驗證

core 基線測試：`tests/test_rule_research_forward_outcome.py` 使用預設長 Windows TEMP 初輪 6 passed／2 failed；兩項 producer publish 在既有長路徑下回 incomplete。改用本次專屬短 TEMP 後 8 passed，未修改核心或放寬 guard。原 UX21 source QA 已記錄相同長路徑限制；此處保留失敗與修正方式。

最終 pytest 同版驗證為 **35 passed**：adapter 27 項＋既有 core 8 項，不累加重跑案例。命令為 `C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe -m pytest tests/test_rule_research_benchmark_adapter.py tests/test_rule_research_forward_outcome.py -q -o addopts= --basetemp=C:/Users/archi/AppData/Local/Temp/ux21bfinal01`。全部使用隔離 fixtures，未讀正式資料庫或個人資料。

覆蓋兩步 pin、ISO／斜線／整數日期格式、same-period core gross excess（target 6%、benchmark 5%、差額 1%）、未知／不同 basis 與幣別、原決策列及 rowset 修訂、同文字不同 SQLite storage type、相鄰 REAL、缺 endpoint／schema／DB、個股 fallback 禁止、名稱不預設、close 欄衝突、晚到／未知 availability、未來 as-of／clock、無效路徑、數值精度上限、唯讀 hash／mtime 不變、取消與 source 變動。WAL 案例以隔離 DB 的真正 writer commit 注入 schema snapshot 後修訂，確認拒絕且無 spec／prices。

兩個 Python 檔 `py_compile`、`scripts/quant_guard_linter.py` 及 diff check 通過。量化 guard 是既有白名單工具，另對本 adapter 做 AST 核對：float literals 0、float calls 0。純 outcome 計算仍沿原 core Decimal；adapter 沒有策略、成本、ML target 或 horizon 選擇。

mypy 首輪 adapter 有一處 nullable availability 比較，修正後單檔通過；含 tests 的檢查有四處動態 fixture 輸入型態錯誤，修正僅涉及測試型別註記。最終 `python -m mypy app_module/rule_research_benchmark_adapter.py tests/test_rule_research_benchmark_adapter.py --follow-imports=silent` 為 **2 files／no issues**；Luna 另以預設 import mode 驗同兩檔通過。兩檔最終 compile 再核對通過；沒有修改測試執行邏輯。UI 未修改，未執行 UI／Native QA，不將此包代稱 UX24 整鏈驗收。

首輪 root／Sol medium 審查發現並交回實作修正：未知 metadata 先建 PricePoint 而錯回 rejected；歷史注入 observed_at 未約束 as-of；缺 main/WAL source-stable guard。另要求 exact 查詢的 duplicate 列上限，避免有界 endpoint 仍讀取無界重複列。第二輪再核對型別修訂、相鄰 REAL 值的精確身份、schema 建立 snapshot 前的來源 pin 與 nullable availability 型態。最終修正與反例結果於下文收束。

最終 Sol medium 只讀審查接受此補丁，未見剩餘阻擋 commit 的缺陷；reviewer 沒有平行重跑 pytest，通過數字由執行收據支持。初輪 tests 的 fixture 欄名、原 capture 時鐘及 same-period excess 預期已修正，再以最終 35 項核對。來源 pin 在 connect 前固定，BEGIN／schema／query／close／回傳前核對；最大四個日期的查詢最多取五列，超量／同日 alias 重複拒絕。型別化列 identity 加 SQLite REAL 的 `printf('%!.26g', ...)`，避免 CAST 文字相同卻漏掉修訂；保留欄名 collision、128 欄／單欄 4096 字元及 Decimal 64 位精度／exponent 上限均 fail-closed。

## 接線剩餘與停止界線

主 owner 需明示 benchmark 選擇與來源 qualification，將合格 adapter 的 spec／points 注入既有 pure outcome core，並納入 source/store envelope 的同版 revision 與重新驗證。既有 actual source 仍傳 `benchmark=None`；本包不替它改接線，也不改 store 格式或日報／UI。

未知 corporate-action basis／官方 availability 的 actual source 不能因 adapter 存在升格為合格相對績效。本包不完成 labels、retraining、正式 daily Task／部署、自然成熟／ML 效果或 Native／真人驗收。UTC 2026-10-06 07:00 安全停止界線有效；完成本地 commit/readback 即停止交回 review。

## 更新記錄

- 2026-10-06：完成 UX21 benchmark adapter 獨立 lane 與同版 35 項測試、獨立審查；來源 qualification 與 actual source/store 接線留唯一主 owner。

## 2026-10-11 後續收據核對

更新記錄中的「來源 qualification 與 actual source/store 接線留唯一主 owner」是獨立 lane 交付時的停止點。後續 `UX21_BENCHMARK_SOURCE_STORE_UI_20261006.md` 記錄 adapter 已接入 explicit benchmark source／store、CLI 與唯讀結果畫面；其隔離 fixture 可比較，但實際公開 TAIEX 請求因 company-action basis／accepted pins 缺件仍為 unknown，excess 為 null。接線完成不等於來源合格，UX21 仍 partial，formal／PIT／training／trading 資格維持 false。
