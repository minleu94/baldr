# UX21 Forward Outcome 研究計算器（2026-10-06）

## 範圍

本 lane 新增純函式模組 `app_module/rule_research_forward_outcome.py` 與合約測試。輸入必須是 UX20 child 或 parent 的 capture/read receipt package，以及呼叫端明示的決策日、日曆、價格點、benchmark、成本政策與 `as_of_date`。計算範圍固定為 H5、H10、H20，採決策日收盤到 horizon 日收盤的 endpoint-only 研究報酬。

基底 `ae64afc0cc9fd6c970a86f3f350053cb7d851d82`；專屬 branch `lane/ux21-forward-outcome-20261006`，worktree 為 repo 的 `output/worktrees/ux21-forward-outcome`。唯一主整合 owner 為 thread `01a10b0e-ccab-779b-b409-3591c1e74041`；本包不修改 dev、不 push 或 cherry-pick。僅新增模組、其測試與本文件，原計畫只讀；`.agents/skills` 不存在，沿既有 `docs/agents/skills/team.md`／`quant_defense_guard.md`，未建立第二套規則。

child 入口為 `build_rule_research_forward_outcome(...)`；parent 入口為 `build_parent_rule_research_forward_outcome(...)`。兩者回傳不可變的 canonical JSON projection；`result_identity_sha256` 由完整輸入及結果內容計算。輸出重讀時會再次驗證 hash、完整母體分母、兩方法 state counts、固定三個 horizon，以及 root/horizon eligibility 必須為 false。

## 狀態與計算契約

- 呼叫端日曆明示交易日、完整覆蓋範圍與來源 identity；計算器不推定週末或補交易日。H5/H10/H20 由既有 `OutcomeMaturityService` 判斷；日曆未知／聲明不完整、決策日不在日曆或 horizon 未涵蓋時輸出 unknown，已知到期日尚未經過時為 pending，不造日期或價格。沒有官方 custody 的明示完整性仍只是研究宣告，計算器不能自行驗證日期列表是否漏了 session。
- 價格只接受 Decimal 正有限值，鍵為明確 instrument/date，拒絕重複點、每 instrument 超過 21 點、超界母體，以及不一致的單位／幣別／價格基準／公司行動基準。只有指定決策日及精確 horizon endpoint 價格時才計算；缺件、停牌、unknown 或 `available_date` 晚於 `as_of_date` 均明示。停牌不跳至下一個可得價格。
- 毛報酬以 `end / entry - 1` 計算；成本公式限定 `proportional_entry_add_exit_deduct.v1`，target 與 benchmark 的 entry/exit 成本都必須分開明示整數 bp。任一端成本未知時保留毛報酬，net 報酬與其 label 為 null；不默認零成本。Decimal 運算固定 256 位 context，顯示 bp 採 HALF_EVEN 整數量化；label 使用量化前 Decimal 正負，不因四捨五入成 0 bp 而改成 zero。
  成本後報酬的固定口徑為 `end * (1 - exit_bp/10000) / (entry * (1 + entry_bp/10000)) - 1`；超額為 target 減 benchmark，相同期間與基礎才比較。這些是呼叫端明示的比例成本研究政策，沒有推造實際成交費用、稅費、滑價或個人交易紀錄。
- benchmark 必須是同一決策／結束日期的 endpoint，價格來源 identity 必須符合 BenchmarkSpec。比較要求 currency、price basis、corporate-action basis 均明確且相容；basis unknown 或不一致時 excess 為 null。成本完整時計 net excess，否則只保留可比較的 gross excess。
- 可得時點逐輸入保留。任何必要價格／日曆的 available date 未知，aggregate available date 為 null、availability status 為 unknown；已知晚於 `as_of_date` 的價格不參與計算。capture/receipt 的 UTC `as_of` 與 `observed_at` 也會作為觀測時鐘下界，不接受早於已知 capture 的 outcome as-of。
- parent 入口逐項核對 parent receipt、完整 captured child 數量、child identity、cohort、日期、decision cutoff、as-of、snapshot hash、`_child_spec`（schema 欄除外）、universe 檔案來源／內容 hash、method contracts 及精確 source_refs。未捕獲 batch 的全部成員（含宣告排除項）在實際 capture state 計為 uncaptured；另保留 declared exclusion flag/reason，母體與每方法 state count 不縮水。原始 selected marker 只按 method rows 計數；selection status 和 selected count 仍為 unknown/null。

## 資格與限制

這是明示輸入的 bounded research calculator，最大 512 個母體成員、每 instrument 21 個價格點；不讀取真實個人持倉、不存正式 Evidence 或 market DB、不呼叫資料源、不 fetch 全市場，也不訓練模型或啟用排程。

計算成功不表示 PIT、正式、交易、執行或訓練資格。capture 保存的來源引用與 hash 不是決策日收盤原始價格的 custody 證明；此處明示輸入的 decision-close 僅為研究錨點，不能證明當時已取得或可成交。日期精度不支援 intraday 可得性；available date 未知時，研究數值可計但 availability 仍 unknown、所有正式資格為 false。endpoint-only 計算不提供 MFE/MAE、路徑風險、期間內停牌完整性或可成交性。calendar 的 complete 是呼叫端聲明，非官方交易日曆核驗。此 lane 不替 UX22 選定任何 ML target。

## 獨立審查與驗證

- 一位 Luna Max 實作，lane root 獨立審查。修正全域 Decimal context 影響、極端合法價格 bp 量化、capture 時鐘下界、重 hash 不得升格資格、缺 slot 的 aggregate availability、unknown benchmark basis，以及未捕獲排除成員的分母；未修改共享服務。
- root 同版 affected suite：outcome、maturity、sample capture、parent capture，77 passed／1 skipped（21.72s）。root 最後把 parent 案例參數化為含／不含排除成員的兩批失敗，明確核對非空集合與每方法數量，避免空 generator 斷言；定向最終 outcome 8 passed（3.02s）。共 78 個不同案例通過、1 個既有 symlink 環境 skip，重跑不重複計數。
- 測試涵蓋 synthetic writer/read receipt、parent 17 included＋2 excluded＝19 的兩批完整母體、精確 children、uncaptured 對照、成熟／未成熟／缺件／停牌／unknown、成本與 benchmark、極端 Decimal／小幅正負 label、重複／修訂 identity、canonical scale、晚到可得日期、receipt tamper 與新 Python 程序逐 bytes 重算相同結果。合成日曆的週一至週五清單只作 fixture，沒有宣稱台股官方 session 或自然樣本。
- 全模組 mypy：`python -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime`，806 source files 無錯誤；兩項既有 untyped-body notes 保留。作者 targeted mypy 亦通過。
- 最終兩個 Python 檔 `py_compile` 通過；既有 `scripts/quant_guard_linter.py` 通過。另對新核心模組 AST 核對無 float literals 或直接 I/O calls；白名單 guard 不作完整未來函數證明，人工審查確認 future 價格只進 outcome，不改原 method/member、選樣或正式資格。`git diff --check` 通過。
- 初次未改基底的預設長 Temp 回歸為 55 passed／1 skipped／15 parent publish_failed；新的短 Temp root 重跑 parent 21 passed（12.44s）。Windows fixture 長路徑限制保留，未削弱 producer gate。最終使用新短 Temp `u21final1`／`u21final2`，保留 fixtures；原始 XML 在本 worktree ignored `output/qa/ux21_forward_outcome_20261006/focused_final.xml`／`outcome_final.xml`，不提交 raw output。
- UI、Manual、config、shared capture/readiness/CLI、正式 DB、個人持倉與原計畫均未改；未做 Native、取網、全市場 fetch、重訓、排程啟用、資料搬移或清理。

## 接線需求與停止點

主整合 owner 後續提供 exact saved package、符合此 DTO 的明示日曆與價格、benchmark 和版本化成本政策；計算器沒有新的 reader、writer、scheduler 或默認來源。序列化 PricePoint 的 `price` 需由呼叫端明確還原為 Decimal；不要把輸出內聲明的 price points 當作已通過 PIT 篩選的資料。保存、consumer／UI、官方 calendar/custody、同日修訂接受規則與自然 outcome 累積仍未接線；ML target／dataset／split／fit 另屬 UX22。

Coverage Pass：本文件保存 API、口徑、結果、限制與接線需求。Snapshot／Architecture／Index／Navigation 及日後 consumer 可見操作的 Manual 同步留主整合 owner 串行處理；本 lane 不越權修改。回滾須先核對 owner 與未提交變更，再由整合 owner `git revert <本包提交>`，重跑限定套件；目前無 consumer 依賴或資料副作用。交付本地 commit 後停止，UTC 2026-10-06 07:00 的全工程暫停約束保持，沒有另建 automation。
