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


## 2026-10-06 dev 主線採納與唯讀 consumer／最小畫面

新整合 owner 由指定 `90d16858c3d0fbdbe06aaaab164ceab947e18cdb`、乾淨 dev 工作樹接手；舊 thread 停止，不重做 learner／Library／personal storage。`.agents/skills` 不存在；已讀根 AGENTS、docs/agents 的角色與 team／quant guard、Snapshot／roadmap入口／現有與目標架構／Manual／coverage。graphify 圖譜沒有 UX20/21 節點且日期較舊，查無關係後改查最新原碼，不更新圖譜或授新資格。全包由唯一 owner 完成，沒有新 subagent。

1304行契約人工 review：exact parent／child count與身份、完整母體、calendar覆蓋／capture時鐘／available_date、Decimal成本／同期間benchmark、未知及排除／uncaptured與固定資格均保留；未來價格只供 outcome，不回填原 method 或 member。不因 core 長度做非必要重構；沿現有 maturity、保存包驗證及 private binding helpers，受影響套件提供相容性守衛。僅三檔 lane diff，無共享 owner 變更；lane worktree focused 78 passed／1 skipped（18.48s）後採納，dev cherry-pick=`25eec766`，原 commit=`9aeb2655854605b5fb3bd383e31d3634d9660ce1`／parent=`ae64afc0cc9fd6c970a86f3f350053cb7d851d82`。

新增 `app_module/rule_research_forward_outcome_reader.py`：明示 receipt＋2MiB內輸入 JSON，驗 parent pin、原 readiness與全部exact captured child包，將Decimal文字還原後呼叫既有純計算器。讀前後核原 readiness、每個child、parent與輸入bytes；拒絕途中修訂，不掃latest、不開DB、不寫outcome、不取網。schema含calendar/prices/benchmark/cost/asof，未知可明示 null，但不造default；asof不能晚於當前UTC日。母體不完整仍保留uncaptured分母。

原每日研究 parent receipt dialog 加結果tab與選檔／清除、方法／horizon下拉；首屏6組狀態與完整分母、成本版本／4項成本，逐股毛／net／gross excess／net excess bp。完整MA20 matched與MA60 notmatched皆可看研究值，selected未知；缺價、日曆不足、pending、成本缺件明示。詳細JSON/hash/source在收合診斷，無畫曲線／勝率／正式操作；generation＋sender guards與合作式取消沿原TaskWorker。結果拒絕保留各批producer/capture記錄，清舊outcome；換parent清輸入，同來源重試重新驗證。

新增 consumer／UI 首輪28案例passed（22.95s）；初次 collection helper `_cost` 名稱誤植，修為現有 `_costs` 後通過，不改產品守衛。截圖 `output/qa/ux21_consumer_20261006/forward_controlled.png` 已實看中文／表格／成本與分母；修正舊next-step仍稱成熟未知的矛盾，pending列不誤稱已明示成本未知。第二輪再加入未完整parent全部uncaptured案例，最終數字見下段。

驗收含17納入＋2排除兩批實際隔離包、逐stock/method完整分母、非零四成本、H5/10/20表切換、成本null保毛值、unknowncalendar／缺精確endpoint／pending、錯parent拒絕保批結果、JSON重複鍵／數字價格／float成本／future asof、child損壞與input途中revision、cancel/stale success/error／單worker重試、同收據新Python程序完整projection逐欄一致及來源bytes不變。既有return/close/newparent/picker守衛仍由原receipt UI套件覆蓋。

Workbench85 passed；update validator25 passed／0failed／4既有skip（隔離Temp fixture DB，不是正式DB）；full mypy810 source files通過、2項既有untyped-body notes。六檔py_compile、quant precision/look-ahead guard通過；guard白名單不代替人工no-lookahead審查。只有pytest cache sandbox警告，非功能failure。所有UI QA offscreen，沒有前景Native、真人或自然來源驗收。未重開性能gate，已接受18.6219%例外邊界不變。

Coverage：Manual（入口／JSON欄位／操作／公式／解讀／限制／排錯）、Snapshot、Current Architecture、Navigation、UI Features、Index／QA入口同步；產品／6M／target／long maturity方向及Gate未改。原plan只追加，output raw與shared_state不stage。rollback先確認owner／dirty tree，再revert本包接線提交；無資料需回復，若連lane一起revert先移除consumer依賴，重新跑focused／UI guards。UTC07:00停止規則保持，完成本地commit與readback即提前停止，不啟新scope。

UX21從pending變partial：純計算器＋exact saved consumer＋最小畫面工程已完成；官方calendar/custody與自然outcome是證據依賴，輸入adapter／outcome持久化與正式daily owner consumer尚為工程，不混稱等待自然。UX22/23未開始。正式Task／data migration／ML fit／交易旗標沒有批准或啟用。

### 最終同版驗證與readback

- dev受影響七模組：107 passed／1既有symlink環境skip，39.85s；其中新consumer／UI及原receipt UI為29個不同案例。命令：`.venv/Scripts/python.exe -m pytest tests/test_rule_research_forward_outcome.py tests/test_rule_research_forward_outcome_reader.py tests/test_ui_qt_forward_outcome_receipt.py tests/test_ui_qt_parent_receipt_dialog.py tests/test_rule_research_sample_capture.py tests/test_rule_research_parent_capture.py tests/test_outcome_maturity_service.py -q -o addopts= --basetemp C:/Users/archi/AppData/Local/Temp/u21finalroot --junitxml output/qa/ux21_consumer_20261006/final_focused.xml`。
- Workbench85、validator25／4skip、mypy810、六檔compile及quant guard通過；最後呈現修正後targeted mypy與diff check再核。初次helper collection錯誤原輸出保留，最終沒有產品fail。
- 原plan追加前211,524 bytes／SHA256 `865687c9d8f57333682ea23f4efdb5acde52fe1ec9eea745e563c0f07eda4cf8`，追加後原前綴SHA一致；原文不覆寫。before／after pins與本包commit/blob對照在ignored `output/qa/ux21_consumer_20261006/plan_before.json`、`plan_after.json`、`commit_readback.json`；raw QA／plan／shared_state不stage。
- 文字校正曾誤用text read/write正規化舊plan換行，前綴校驗發現後，以既有UX10 plan_before備份的相同內容前綴還原原換行；最終211,524bytes原前綴SHA完全一致。沒有刪改原計畫內容或放寬「只追加」。恢復方式與最終hash保留於plan_after.json。
- 新程序readback、UI測試子程序都正常退出；沒有派出仍工作的subagent或Native程序。完成接線本地commit/readback後本owner停止交父層，不等截止才停，也不開UX22或部署。

## 2026-10-11 後續 UX21–UX23 收據核對

上文「UX22/23未開始」及純計算器尚待接線，描述的是 2026-10-06 本包主線採納時的停止點。後續 [UX21 benchmark source/store/UI 收據](UX21_BENCHMARK_SOURCE_STORE_UI_20261006.md) 記錄明示 benchmark adapter、保存、CLI 與唯讀畫面已接線；公開 TAIEX 仍因 basis／accepted pins 缺件而 unknown，UX21 仍 partial。後續 [UX22 label readiness](UX22_LABEL_READINESS_20261006.md) 與 [UX22 同源公平比較](UX22_FAIR_COMPARISON_20261006.md) 記錄有限 readiness／事後比較工程，沒有真模型 fit 或 qualification。後續 [UX23 registry integration](UX23_REGISTRY_INTEGRATION_20261006.md) 記錄唯讀 registry consumer／CLI 整合，但正式資格仍全 false，沒有啟用正式 shadow。這些後續切片不把任何 UX 或 Stage 推定為整體完成。
