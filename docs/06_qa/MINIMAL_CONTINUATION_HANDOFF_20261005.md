# 最小續接清單（2026-10-05，Batch9）

## 最新優先：UX16唯讀來源契約與UX02 Native中文

以dc14c080為基線新增source contract／CLI及loader opt-in timing／strict SQL，原預設caller不變。Root最終21passed、mypy3files、compile4檔、quant guard通過；9個UI blob不變，沿用85／25+4skip。正式D兩檔3日6列穩定研究讀取、scoped hash保留；availability未知、cutoff-screened0、PIT／formal training／published snapshot false。所有已知／未知／拒絕與前置失敗見[UX16限定收據](UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)，不要重跑60檔審查／learner／1477／效能baseline。

四用途Native代表畫面已用既有JhengHei清楚顯示中文；三頁受控，個股記錄DTO明示SHA／331.0／10-05／ML unavailable，非此run即時DB。前三失敗保留；四輪driver／launcher均退出。未改產品UI、OS設定或使用者視窗。Native畫面不授新自然資格，不替代1000×835已接受與1000×800限制。

原plan只追加本包結果；stage1 Backtest18.62%仍低於20%原門檻，不宣告全部通過。下一包先按父層裁定處置stage1與UX16缺證據，再選具單位／版本／暖機依據的共用feature dictionary與增量等價性；UX19需原universe／decision manifest／完整性／原子發布／revision／容量，不啟UX18新方法或正式writer。當期研究可以具名復用，歷史PIT未知不當全產品阻塞。Phase3C法人lane本包未讀；若後續復用9/29個股與10/2aggregate，須另核同版identity。

本地commit/blob/status收據留 `output/qa/ux02_native_source_contract_20261005/`，以Git實際HEAD為準。無push、producer、訓練、永久清理或大DBcopy；未知paper檔與C:/ta_iso_1005保留。本批完成後停止，由父層安排下一批。

## 2026-10-05 小型 learner／Library 收尾（本節優先於歷史待辦）

接手核驗：`dev` HEAD `cd908443fe8a4afb098a5103e70ff6fe728ef6aa`；只有未知未追蹤 `paper_event_source_capture.py`，未讀、未改、未提交。既有 checkpoint、60 檔有界審查與 UI gate 不重做。

- 補強 `test_real_runner_writes_only_current_observed_research_candidate`：180 筆／20 特徵、360 筆重複輸入經真實 semantic dedup 回到 180 筆；重驗 capture／outcome 綁定後實際執行 learner、候選寫入與收據讀回。錯 entry source hash 在 learner 啟動前拒絕，沒有隔離候選產物；既有正式區與 canonical marker bytes 不變、active pointer 不存在、promotion／formal 資格均未取得。
- 來源驗證器使用受控 fixture（非官方原件或自然 producer）；learner、候選、lineage／receipt 是實際執行。結果 `fitted_research_only`，candidate `rec-cal-eef7ecbbcd02e49e5f57d98f`，dataset hash `sha256:428ca5f4c617a9652bf9c6dadd34bc2ab0e9632e2f3ca5081ff1baa4afe45b3a`。收據 hash `sha256:41bbb1958aaad358ec195b16dfe5addd6090f7f53e9effb4a116c7b8aea4d796`。測試暫存依原 fixture 結束回收，JUnit 保留身份；不冒稱原件仍留存。
- 最終單模組 pytest **19 passed／1 Windows symlink skipped，0.99 秒**；changed-test py_compile 與 diff check 通過。前置四個精確 nodes 4 passed，之後增加 JUnit 身份輸出才重跑此單模組；沒有全套或 UI 重驗，也沒有正式 DB／registry 寫入。
- 三張圖已保存使用者 Library（見下表）。全部為 `cd90844` 最小 UI 切片的**受控 DTO／offscreen**圖，不是真實模型、Native 或自然資格證據。雲端保存成功；Windows helper 不支援本機版本屬性寫回，ID 對照另存收據。
- 原始 QA：`output/qa/bounded_learner_library_20261005/pytest.xml`、`receipt.json`；指定原計畫原位更新，保留修改前副本 `plan_before_batch.md`。output／暫存不提交。

| 圖片 | 正式 library_file_id | file_id |
|---|---|---|
| `2382_summary_controlled.png` | `libfile_d0e11bd2f2b08191b4606269aded4421` | `file_0000000043dc81f4afc7e59ff82b5c42` |
| `2382_ml_collapsed_controlled.png` | `libfile_978664747334819186cbe7fb4dd6dd5c` | `file_00000000aa8881f4b90cc9edcd1922c4` |
| `2382_ml_audit_controlled.png` | `libfile_452fcff4b41481919827de371cdbd486` | `file_000000005d6c8243aa5e2a701547c2c5` |

尚待另批：Native 1477 真正取消完成→重試→新身份→正常保存→新程序重開，以及錯 date／run／hash。1000×835 outer／125% 已接受，1000×800 未達保留限制，不新增硬門檻。D 正式 raw-PIT 與清理沿用既有具名依賴；本批沒有重做容量 guard 或清理、沒有操作使用者 App。

後續明確指示已保留：先完成現有 Native 驗收及逐次具體批准的暫存清理，全部收尾後再按唯一 `output/plans/baldr_product_experience_plan_20261004.md` 推進，由 **Sol Medium＋Fast／GPT-6 Luna Max subagents** 分批實作，父層負責規劃審核。此新授權適用後續計畫階段，本批不開子代理、不跳到大計畫、不 push；永久刪除未獲隱含授權。

回退：本批只修改整合測試與兩份交接文件，可針對本批 commit 作 Git revert；ignored 原計畫可從修改前副本復原。Library 檔案保留，不因本機回退自動刪除。Manual／產品／架構無行為變更，不把本次工程測試改寫成正式產品完成。


本文件只供方案變更後續接，不取代目前狀態 SSOT 或宣稱工程全部完成。本輪只補最後一次 native 單步取證、逐檔提交審查及清單凍結，未修改產品、新增 DB、重訓、全回歸、stage 或 commit。最後一次 probe 已停止，不再追加嘗試。

## 已接受證據

- 分支 `dev`；HEAD `13f7a410c2ad850d981ed552ef09515220718ade`。先前工作樹有 217 個變更路徑、index 空；不得盲收根目錄未知 `paper_event_source_capture.py`。
- 工程七項驗證沿用 `output/qa/g11_sol_batch3_20261005/final_independent_readback.json`：Workbench 85 passed；validator 25 passed／4 skipped；全域 mypy 766、scoped mypy 38；120 模組回歸 1892 passed／12 Windows symlink skipped；222 路徑 compile、量化防禦檢查通過。不能用此取代完整原生 UI 驗收。
- G11 公開 service 真實讀回：`output/qa/g11_sol_batch1_20261005/public_service_real_receipt.json`。TDCC 為既有官方原件受控搬移，非新 HTTP 成功。
- G6 既有 CORE19 十股模型 train/save/public load、G9 15／17／50 股受控 cohorts、Forward 既有處理證據保留；本批未重跑。G9 最後 53 個 producer pins 未變。
- 固定程式 inventory SHA256：`4a4a22643b561db60cd7884c1c8bbe0b54db9dc8ce3262bd35b61899492a6904`；測試：`55d496cc384aa2f9706657dbcda3da5ec94ac2e7c360f88ac79139e1c960a151`；ML 儲存設定：`39198481b876830d195388bfa54930c6e84c28a7ebec358550a6d4c8a3763ccc`。後續若改動，應按影響範圍重新驗證。

## 三項 UI 判定與最小後續

1. **current-ML Advice／Rule：內容存在；harness 在新控件可見前立即斷言。** 單步原生使用既有隔離資料與精確來源 `rec_3a882dd9fc06407298ccbd2a5e1c994f`，1477、決策日 2026-10-05、行情日 2026-10-02；request 1 保存 → 2 current → 3 返回保存。`reportLoaded` 時 group 已建立但 `isVisible=False`；Qt 事件處理後新 Advice、當下技術／Rule、原保存 Rule 可見，保存 Advice DTO 完整相同。原生截圖及返回保存模式實際點擊成功。最小修正是 future harness 等待同 request／stock／source／date 的活頁控件可見，不修改產品或放寬內容斷言。本次診斷在 125% 進行，原 100% 整個 source-recovery 尚未重驗。
2. **取消／重試：UTF-8 啟動問題排除；runner 漏選 lazy Rule 分頁。** 正確環境已實際啟動 UI，`cancel-retry-20261005T031447-963aa2f084.json` 停在 `create_analysis_button` 不存在。原生失敗畫面是「摘要」；產品只在 `_render_decision()` 建立此按鈕，單步 Rule 頁已確認按鈕可見、可用。因此不是按鈕被產品移除。最小修正是先進 Rule 頁並等待按鈕；本批未改 runner、未再次執行推薦取消／重試，真正取消、丟棄部分結果、重試及保存尚未驗證。
3. **1000×835：內容 min-size 與 frame/client 換算，不是指定尺寸已通過。** Win32 外框 `[20,20,1020,855]`；client `[28,51,1012,847]`（984×796）；Qt 內容 787×637 邏輯像素，最小高度與 layout minimum 均 637，DPR 1.25。637×1.25 約 796，再加 39 外框成 835。必要來源、建立分析、模式按鈕可見且有 visible region；current／保存切換實際成功，Advice／Rule 以捲動閱讀並有截圖。最小後續是明確以 client 還是 outer 定義驗收尺寸並評估原 800 實體高度需求；若仍要求 outer 800，需另行批准處理實際 layout 最小高度。未放寬原 1000×800 斷言，也未宣稱所有頁面無裁切。

診斷證據：`output/qa/g11_sol_batch5_20261005/single_step_native_readback.json` 與同目錄 PNG；舊原生局部失敗：`output/qa/g11_sol_batch4_20261005/final_independent_readback.json`。沒有可用 CUA 工具；使用 Windows 平台 Qt 實際點擊、Win32 讀取與螢幕截圖，不是 offscreen。

## 有限實際行為補驗（Batch6）

- **精確重開通過**：新 process 啟動時未自動套來源，以可見 exact ID 讀取入口重開原始 receipt 的 canonical 篩選紀錄；1477 原未入選原因、result ID 與保存檔一致。未偽造原 source-recovery 的 success 標記。
- **錯來源／錯股拒絕通過**：不存在的 exact ID 顯示讀取失敗並保留原完成結果；2382 頁不包含 1477-only 的原保存來源。僅將該真實 ID 作為可見 combo 的 QA 負向輸入，點擊後顯示「請先明確選取保存來源」，request 未增加、context result ID 仍空、沒有借用 1477 Advice；QA combo 輸入未持久化。錯日期／獨立 run/hash 負例未在本批補驗。
- **真實取消已執行；取消→重試整段仍未通過**：由合法 Rule 分頁的建立分析按鈕進入推薦，scope 1477，真實 worker generation 2 啟動後點擊取消，terminal 為「已取消：沒有套用部分結果」。所有既有 recommendation JSON 保存檔雜湊不變；UI 仍保留原 canonical result ID 與原篩選列。單步 probe 誤沿用「取消後 current_execution/result ID 必須空」的舊判準而停止重試；這不是產品 bug 的證據。產品 `_on_recommendation_cancelled` 保留既有完成內容且不套用部分結果。原 probe 失敗保留，沒有改寫為整段 PASS；**重試至完成及其新 stock/run/date 證據仍缺**。
- **1000×835 實際小視窗已逐頁讀取**：盤勢總覽、持倉、推薦，以及個股研究六分頁，共 32 張原生 PNG。盤勢主結論與研究入口、3 筆使用者持倉與個股入口、1477 推薦 scope／執行按鈕／保存結果讀取、個股價格／基本面／籌碼與 source/mode 控件在畫面或捲動範圍內。1477 非使用者持倉，Health/Exit 明確顯示不對非持倉推導動作，未補造持倉。
- 尺寸仍為既有 layout 最小高度 637 邏輯像素 × 125% 與外框造成，**原 1000×800 未達**。在實際 835 高度可閱讀與捲動；窄視窗的表格仍需水平捲動。部分研究頁捲到極底有空白尾段；未將此當資料內容通過，未逐個展開進階、逐格驗證表格或實際點擊所有按鈕。可用工作區高度少於 835 實體像素的螢幕可能受最低高度限制，不能宣稱所有一般螢幕皆無阻礙。

原始行為收據：`output/qa/g11_sol_batch6_20261005/actual_behaviors.json`；獨立核對與限制見同目錄 `final_behavior_readback.json`。Batch6 未修改 production、既有 runner 或原失敗收據，未修工具追加重試。

## 最後一次取消／重試（Batch7）

- 在同一隔離資料、單一 UTF-8 原生 process 重新做合法 Rule → 分析 → 取消 → 再分析，**沒有重跑完整 runner**。
- 取消 generation 2：舊完整 execution/read model、canonical result ID 與可見表格的序列化 digest，於執行中及取消後均相同；所有既有 recommendation JSON 檔案雜湊不變，terminal 明示不套用部分結果。此次使用正確保留 last-good 的期待。
- 重試 generation 3：執行中仍保留原完成結果；實際出現正常「篩選紀錄／未入選」訊息框，經原生畫面核對後只按可見 OK。最終原生畫面顯示新的 1477 單筆未入選紀錄，原因 `liquidity_volume_ratio_below_min`，取代原估值原因；未自動保存新的結果，原 canonical artifact 雜湊仍與原 receipt 一致。
- **完整身份綁定驗收仍未通過**：正常資訊 modal 的等待／人工核對耗盡單步 probe 90 秒期限，按 OK 後走到 timeout 分支，沒有保存新 completed execution 的結構化 result/run ID、決策日／行情日。這是本次取證缺口，不能以原來源日期或新 generation 猜填新 run，也不能當產品重試失敗。沒有再執行第二次重試、修產品或更改原失敗收據。
- 後續僅剩在一次適當處理正常資訊 modal 的原生觀測中保留 completed execution 的新 run／日期／股票／未保存狀態；取消的 last-good 保留與原 artifact 不變已有直接證據，不應重列為清空舊結果要求。

證據：`output/qa/g11_sol_batch7_20261005/retry_once_receipt.json`（原始 timeout）、`pending_windows_readback.json`／對話框 PNG、`normal_terminal_dialog_ack.json`、`true_terminal_or_verification_failure.png`；獨立核對見同目錄 `final_retry_readback.json`。本批未 commit。

## Batch9 最後一次 native 嘗試與提交邊界

- 最後一次正確 UTF-8 native probe 已停止，**後續重試未啟動**。cancel generation 2 的 worker 結束時 UI 仍「取消中」；probe 就緒條件提前返回，後續要求「已取消」的檢查失敗。last-good 與兩個原 artifact SHA 均不變。這是 probe 終態等待缺件，不足以判定產品取消失敗；不能把本次「取消中」列為取消 PASS。沒有 completion events、沒有新 retry generation、沒有新保存結果；未延長 90 秒上限或追加嘗試。原失敗保留於 `output/qa/g11_sol_batch9_20261005/native_retry_final_receipt.json`。
- Batch8 只讀補證確認 Batch7 process 已結束、保存 store 仍只有原兩筆；`output/qa/g11_sol_batch8_20261005/timeout_after_readonly_supplement.json` 不改寫 timeout，不能補出新 run/result ID、日期或來源身分。
- **自然 ML 容量仍是實際阻礙**：Batch1 歷史讀回 C 可用 211,644,039,168 bytes／研究需求 215,285,235,712 bytes；D 可用 281,449,877,504 bytes／正式 raw-PIT 需求 295,279,001,600 bytes。這不是本輪即時容量量測，也不保證已恢復；不降低 reserve、不套用未量測壓縮率或刪除資料。
- 官方 DNS／外部來源、歷史月營收／季報 availability map、coverage／units／basis 與正式 PIT／revision 資格仍須核驗；現況可讀不授正式估值、歷史回測或正式 ML 資格。Forward／H5／Paper 真正未到期可留待交易日累積，缺到期行情／來源／治理證據則是具名缺件。不能宣稱只剩自然累積。
- Native 尚缺完整取消→重試→新 execution 身分→正常保存→重開，以及錯日期／錯 run/hash 驗收；**1000x800 未過**。21 個 task Ready 是先前受控／唯讀觀察，不證明新自然 run 已成功；權限不可讀保持 unknown，不改 ACL。
- 目前 218 個變更路徑／217 個候選，index 空。v12 是 209 個候選的 provisional inventory；目前 200 個 bytes 相同、8 個新增路徑、9 個內容變動。本輪 `output/qa/g11_sol_batch9_20261005/` 逐檔審查與 checkpoint whitelist 保存精確路徑、SHA、HEAD diff 與同版 gate pins；舊審查狀態逐檔保留，不因測試通過自動升級完整語意審查。
- **本輪不 stage 或 commit**；凍結清單供父層審核 checkpoint，並非全部產品完成批准。任何檔案、HEAD 或 index 改變均須重驗；QA 清單不提交，未知根目錄 `paper_event_source_capture.py` 僅保留檔名，不讀取／雜湊／提交。禁止 `git add .`、push、amend、reset/clean 或覆蓋未知工作。

## 容量、自然累積與提交

- 容量阻礙沿用 Batch1 量測：C 自然 ML guard 約少 3.64 GB；D 正式 raw guard 約少 13.83 GB。這是當時量測，後續需重新讀回，不能視為即時餘量。本批未清理檔案、移根、降低 guard、改排程或 OS 設定。
- 自然排程成功不能用受控 receipt 替代；歷史 PIT／可用日期及成熟度保護不得猜填或取消。Forward／H5／Paper 資格仍依真實時間累積，外部來源／DNS／官方歷史證據限制另看既有報告。
- **Commit 未完成。** 後續先確認活躍 writer 與工作樹，完成剩餘有限原生驗收，再逐檔審 diff／依 git exclusions stage 必要程式、測試、文檔與依賴；不提交 DB、raw、runtime、credentials、未知檔，不 push／amend／reset／clean。
- 目前未完成的原生項：完整 source-recovery、錯日期／獨立 run/hash 拒絕、重試 completed execution 的新 run／日期結構化身份綁定、原指定小視窗尺寸及完整四用途內容驗收。重試的新 1477 未入選畫面已在 Batch7 實際出現，不能將取證 timeout 當產品重試失敗。精確重開、錯來源／錯股拒絕已由 Batch6 單步補驗，不應重列為未驗證。已接受工程結果在固定 inputs 不變時可沿用。

## 2026-10-05 Native 可行性與最小 UI 追補（基線 0831633c）

- 唯讀桌面核驗：前景 ChatGPT；Python 程序為 MCP／formatter，未發現正在執行的 baldr UI。沙箱前景 handle=0／CIM denied 不代表桌面空閒，改以獲批准的唯讀核驗取得真實前景。沒有操作／關閉既有程序、鍵盤、滑鼠或持倉。Native app 控制未開放；舊驅動 `window.show()` 與 modal 不能保證不搶前景，因此**本輪沒有啟動 Native 流程**。需協調短暫桌面時段，不能以 offscreen 替代。
- 1477 舊保存來源 `rec_3a882dd9fc06407298ccbd2a5e1c994f` 的 public query 在 41,453 bytes 小型 artifact／index 副本中讀回；重新編碼錯決策日、換 result/run ID、變造 index payload hash 三項均遭完整性拒絕。原 artifact／DB hash 未變。原封存事件證明 decision=2026-10-05、market=2026-10-02、invocation=`rec_3a882dd9fc06407298ccbd2a5e1c994f:9bbae285d1da44018eba40e6f3b3ae35`，market fingerprint=`cac39aaa588692578b88497d0e3fb2f58b557d740f73ea3aad8948ffbe22182c`。這是原保存來源完整性拒絕，**不是新 retry run、Native 選擇日期／run／hash 驗收或保存重開成功**。
- 確定小 UI 缺陷已修：ML 稽核按鈕依 toggle 狀態顯示展開／收合。DTO 明示 current scope 才標「當前ML研究」與研究日；saved scope 標「所選保存決策ML研究」與模型事件日，未知 scope 維持中性標題。歷史保存決策回顧顯示已讀回 Advice／保存分析日期；沒有所選日期時標未選定。品質降級呈現來源限制，無原因時明示原因未提供；沒有改計算、來源、資格或 hash 契約。
- 真實 2382 唯讀 current consumer：as_of=2026-10-05，ML event_date=2026-10-02、run=`20261002-ffb8777d33621369a15c3c22`、scope=`current_stock_research`；degraded 原因為「H5 標籤尚未成熟；不顯示報酬或成功結果。」已確認可見。沒有注入持倉服務，首屏只是 DTO 的 offscreen 投影，不是完整 MainWindow／Native 驗收。TWStockConfig 的 D 槽 config log 寫入被沙箱拒絕並回退 console-only；未實際寫入正式資料或 registry。
- 真實首屏 Library：`libfile_d7d04064bca881918a985dcada1ab24b`／`file_0000000054f88210b0ea43e50941efb7`。雲端成功，本機版本屬性 helper 在 Windows 不支援，身份對照保存在本批收據。
- affected tests **14 passed**；Workbench **85 passed**；validator **25 passed／4 skipped**；全域 mypy **766 files／0 issues**；兩個 changed Python py_compile 與 diff check 通過。新增測試的兩次失敗是 lookup 抓到 `deleteLater` 舊 group，最終改用獨立 view 觀察各狀態，未改產品 renderer；失敗 XML 保留。1477 負例全部完成後，最後 stdout cp1252 編碼失敗，收據與三項拒絕已落盤且獨立讀回，沒有重跑此負例或改寫 process exit 0。
- 原始證據：`output/qa/native_feasibility_followup_20261005/`，含 final affected XML、Workbench XML、validator／mypy log、真實 DTO／畫面、1477 完整性負例與 Library identity。原計畫原位更新。僅 stage 必要 UI／測試／Manual／功能文件／Snapshot／交接；output 與未知根檔不提交，不 push。

最小下一條 Native 流程已限定：獨立 QA settings／小型既有隔離來源；1477 原來源→Rule 分頁→scope 1477→開始→取消後必須等 `已取消` 且 worker 結束→檢查 last-good 與原 artifact 不變→一次重試；正常資訊 modal 只確認可見資訊，完成以新 execution/result/invocation 與 completed 終態綁定→正常 Save→保存 receipt/hash→新程序精確讀同一新 result。日期／股票／run／source／hash 在每一步從該步實際結果取證，不沿用舊 run；獨立 Native 負例另驗。每步沿用 90 秒上限，不反覆修跑；若失敗，停止並分清產品與驅動缺陷。本輪未執行上述流程，完整 Native 待辦保留。

桌面時段未確認前不顯示 QA 視窗，不修改使用者視窗與資料。暫存清理與大計畫維持前批順序及 Sol Medium＋Fast／Luna Max 後續配置。本輪不 producer、重訓、子代理、cleanup 或外觀擴張。回退僅針對本批 commit 的 UI／測試／文件；原計畫追加段落可還原修改前副本，原保存來源未變。

## 2026-10-05 使用者授權桌面 Native 有限驗收

- 本批基線 dev `e312dc61141d7f0a812466e0ba5f7c0b56ecbbae`，使用者明確授權桌面；僅 PySide6 QTest 的 Windows Native 隔離驗收視窗。無 node_repl Native 控制工具。未訓練、未執行 producer／全套回歸、未修改正式資料／排程／持倉、未刪暫存。
- 首次 sandbox 程序在原來源載入後 screen grab 失敗，尚未取消／重試；以已授權 desktop access 執行相同流程，不計為產品失敗。
- 1477 精確原保存來源 `rec_3a882dd9fc06407298ccbd2a5e1c994f` 成功載入（決策 2026-10-05／行情 2026-10-02）。取消 generation 2 確认「已取消」且 worker 結束，完整 last-good UI 與原來源 JSON 保持不變。
- 重試進入 generation 3，但 `completed retry` 等待逾 90 秒：無完成事件、無 worker_finished_objects、無新 completed result 身分。harness 記錄 TimeoutError 後關閉自己的視窗並退出。新身份→保存→新程序重開，以及新 run 的錯 date/result-run/hash Native 拒絕 **仍未驗收**；不能拿舊來源完整性負例替代。重試超時是工程／驗收阻礙，原因尚未定位，不能稱為等待自然成熟。本批沒有再次重跑1477。
- 外部停止只嘗試 PID 綁定核對，當時 QA PID 已不存在，未停止任何程序。中間推測 mouseClick 未返回已由最終收據更正：實際進入 completed retry 的 bounded_wait，generation=3。桌面已釋放，自己的1477與2382 QA程序均退出；其他應用未關閉。
- 2382 用真實只讀 consumer、Native 報告視窗正常 load_button→背景worker完成，非 MainWindow 全流程／持倉驗收。為禁止正式目錄與 logging 寫入，僅在 config 初始化封鎖該寫入，consumer 讀取與回報未替換。初始 badge/提示更新為「部分可用／報告部分載入」，as_of=2026-10-05，行情 2026-10-02/收盤332；ML current_stock_research run=`20261002-ffb8777d33621369a15c3c22`、source hash=`76368e75edaa665ee363cc25506687288f3ddeb2475c40cdb4c933fb16ba8d2e`，與先前真實2382來源一致。
- Header 疑點拆開：正常 load 沒有殘留「尚未載入」，證實該初始狀態源於 offscreen 直呼 render 未走 loaded callback；但未選定保存來源時「來源：未標示／決策日：未知／資料日：未知」仍存在，下方獨立行情來源另有2026-10-02。這是未提供 source context 的文字歧義，未取得資料混用證據，不直接判為產品 bug，也未改 UI。若要確認 MainWindow 選定來源脈絡需另批有限驗收。
- 1000×835/125%既有接受限制沿用，不重做尺寸工程；本批不宣告1000×800通過。沒有產品修改，沒有新增/重跑tests。
- 收據／截圖：`output/qa/native_acceptance_authorized_20261005/native_retry_final_receipt.json`、`2382_normal_load_receipt.json`、`library_identity.json`。2382圖正式Library `libfile_3dbdfe10c6c48191bd65b687bb8b7444`（`file_000000006d3081f4bf3bd49b257c7d4e`）；取消圖 `libfile_57e26618f2a081919724e90426e8be2a`；超時圖 `libfile_65f3870d3a908191998117af696e853c`。這批為 Native QA 證據，仍不是自然模型成熟證據。
- 下一批由父層裁定1477重試超時的有限診斷；暫存清理盤點已交付但未執行，仍須遵守先Native閉環→已批准清理→唯一原計畫的順序。永久刪除另需逐項批准。

## 2026-10-05 Generation 3 重試超時診斷（未再開 Native）

- 結論：實際重試超時根因仍未知；已確認 driver 缺少 timeout 當下 worker/phase/error/stack 的觀測，不能回推90秒時是否仍運算、等待IO或signal遺漏。沒有明確產品bug，未修改產品程式，Native仍未通過、工程未完成。
- 先前成功1477 strict-PE從03:08:25.013198Z開始到03:08:29.711005Z保存讀回約4.697807秒（包含modal/save）。當時native_runner_v23.py的_wait用processEvents+time.sleep(.02)。本批qWait(1)小型離屏A/B為0.359秒對0.047秒，證實可增加等待延遲，但不能外推或證明真實90秒根因。Batch7亦曾generation3超時，其pump已用Python sleep；因此不能把兩次缺口都歸因qWait。Batch9沒有開始重試，是取消中誤判。
- timeout截圖仍分析中/舊結果，dialogs=0、completion_events=0、額外finished callback=0；沒有timeout isRunning/isFinished、progress/error/native_finished或stack紀錄。completed handler原本會先更新UI後開modal，支持當時不是完成modal卡住，但證據不足完全排除其他瞬時問題。
- 靜態路徑每次建立新ProgressTaskWorker，cancel event預設false，_begin_execution_status重設UI cancel flag；隔離離屏cancel generation2→retry generation3完成及native_finished通過，22事件、新cancel flag=false。這僅驗證Qt訊號/執行緒，不替代真實Native。既有兩個精準測試2P/1.44秒（pytest cache permission warning），沒有全量重測。
- graphify只查既有graph導引（72相關節點/427鄰邊），未重建或開子代理；目前HEAD原始碼為權威。沒有操作桌面、真實推薦/資料查詢、producer、learner、刪除或壓縮。
- 修好的隔離driver `output/qa/native_retry_diagnosis_20261005/native_retry_instrumented_not_run.py` **尚未執行**，保持90秒及原接受條件；恢復sleep(.02)，pre-start接全部worker訊號，記錄run-enter/exit、thread id/generation/ns time、實際retry config/scope；timeout保存worker flags、UIphase/progress/last_activity、result identity與Python全thread stacks；modal保留wrapper避免id重用漏記錄。`worker_diagnostic.py`已py_compile，觀測器離屏探針exit0。首個探針末尾stdout cp1252錯誤已保留，修UTF8後另用probe_utf8成功，未覆寫舊證據。
- 最小後續：父層安排新的桌面時段，先核對原來源/inputs/hash與retry config差異，只跑同一1477一次。遇error/timeout立即讀phase/stack/terminal紀錄，不延長期限掩蓋、不再盲跑；僅正確completed新identity才繼續save→fresh reopen→新run date/result/hash負例。依合作式shutdown安全收尾，不能強制terminate持有資料資源的thread；未安全退出就明示worker/桌面狀態。
- 完整證據及策略：`output/qa/native_retry_diagnosis_20261005/README.md`、pump_probe.json、probe_utf8/receipt.json、affected.xml、graph_probe.json。本批只修ignored驗收driver與文檔，沒有用fixture pass宣告Native接受，清理/roadmap順序保持。

## 2026-10-05 09:23 UTC：Native有界操作鏈已完成（更新較早待驗）

- 本次基線770625cd，遵照使用者09:11UTC授權直接操作；1477 generation2真正已取消、native thread完成且last-good保留，generation3在4.5秒完成並保存新來源 `rec_e677f9ba56d84a5cbcd6f18d5778a01c`。新程序PID34768與首次35148不同，完整execution/result/hash一致；決策2026-10-05、行情2026-10-02。payload `sha256:708fcd18c1980817203549d7a81440811c01a5677d39642e1d26cd6d9c0b5802`，raw artifact `sha256:40c62704e28ccd1f52e724de456b7b1af93942f0e6b90d62b590ff6f0e822965`。
- 本次正常UI新分析設定為PE999／volume ratio min1，因量能未入選，與原PE1的舊來源原因分開記錄；不得稱為推薦成功或原run。新來源Native截止日10/4拒絕10/5未來Advice；42,087-byte隔離副本的artifact日期／result-run／index hash三負例拒絕且保留同一last-good，原artifact/index不變。缺少source_snapshot_hash的欄位仍留空，沒有代填。
- driver觀測修正後真正重試一次就完成。讀回driver誤查Request.universe的失敗保留，改讀sealed config；metadata通過但畫面擷取偏早的版本也保留，最終reopen3加可見提示／表格條件及repaint350ms並實際看圖。只重開讀回／負例程序，未重跑已完成分析；沒有產品修正，不延長90秒。此前超時根因因原telemetry不足仍不回填為已定位。
- [完整Native驗收](NATIVE_1477_RETRY_READBACK_ACCEPTANCE_20261005.md)及本機output/qa/native_retry_completion_20261005/acceptance.json、attempt1/native_retry_final_receipt.json、reopen3/reopen_negative_receipt.json、library_identity.json為最終證據。新程序圖Library `libfile_4a0caaa465ec819188c4b880b112470c`，錯hash圖 `libfile_0583c30490608191981996418201059c`，其餘3圖ID見驗收表。
- 四個自己的QA程序均退出，09:23:01UTC核對PID全無，桌面釋放。未修改正式資料/持倉/排程、未訓練/producer/全量tests、未清理、未push。本次僅完成原Native工程鏈，不授自然成熟/正式模型/PIT資格；1000×835/125%沿用，不宣告1000×800。2382header前批正常load結果保留。
- Native已達標，交回父層安排安全清理，再依指定原plan分階段推進；永久刪除另需逐項批准。原plan正文保留，追加本收據，不另開替代計畫。

## 2026-10-05 可恢復暫存整理已交付

- 1251原白名單中879根同C盤隔離至C:/ta_iso_1005，642純pytest fixture、229空根、8mypy快取，108054檔、AllocationSize前後4,951,450,624bytes一致；不釋放檔案容量，未永久刪除／清空回收筒／改權限。r015 d/e/f成功，g/h/i保留；R20/R26 user Temp136空根成功，具QA引用的群組保留。372根保留，58引用根及19占用／權限未通過者均未動，精確理由／映射／還原步驟見[整理收據](TEST_TEMP_REVERSIBLE_ISOLATION_20261005.md)與output/qa/reversible_cleanup_20261005。實際r015 d還原並重新隔離、全879項identity核對通過。
- 最新只讀容量：C free237,505,548,288／既有需求215,285,235,712；D free300,638,941,184／既有需求295,279,001,600，兩者點時間PASS；不歸因本批隔離，不啟動writer，實際writer前重新查核。本批必要永久刪除清單為空；若要真正釋空間，879項未批准候選另需逐路徑批准。
- Native不重開：此前driver的pre-start訊號／run與timeout觀測、sleep(.02)等待及讀回sealed config／paint條件修正已記錄；歷史90秒根因仍未知，最終4.5秒真實鏈已接受。未開代理／producer／訓練／全量tests，未動正式資料／模型／持倉／排程。本批結束交回父層，按唯一原plan啟動後續階段。


## 2026-10-05 原產品計畫階段 0 首包

沿用原計畫，UX01有界基線／UX16來源子集／UX17量測已交付；產品程式未改，階段1優化尚未開始。首屏median10.148秒、資料10.126秒，30次列選取高亮p95=116.60ms；不能當篩選／圖表驗收。首次市場探索Overview worker發生重資料切片，loaded全程CPU60.94秒／RSS1.57GB、約90秒合作退出，是下一包工程入口，不歸因自然成熟。來源／正式資格／暖機／全市場與benchmark缺口仍見矩陣；原UX依賴不跳過。

完整結論／同版hash／失敗紀錄／兩位Luna工具派發及自省限制見[效能基線](PRODUCT_STAGE01_PERFORMANCE_BASELINE_20261005.md)及[來源矩陣](PRODUCT_STAGE01_SOURCE_MATRIX_20261005.md)。五個child與輸入guard通過，PID均退出；外層末尾Unicode print exit1保留，提交版僅輸出與CPU命名收尾，基線未重跑。不重開已接受的1477／learner、不producer／訓練／全量回歸／永久刪除／push，unknown根檔及還原隔離均保留。本包本地commit／blob核驗後停止交父層。


## 2026-10-05 階段1限定效能修正包

兩位指定Luna Max完成7個產品檔及6個test檔修正，root整合；profiler及main未改。日期解析單次memoize、回測／組合首次圖表lazy與可見錯誤重試、同輪盤勢整批近期價格及合作取消／native-finished關閉已驗。同條件5跑首屏10.148→8.642s（14.84%）、Industry3.206→1.842s（42.56%）、Backtest1.098→0.893s（18.62%），完整rowset SHA不變；四筆只啟動RSS約0.70→0.57GB。Loaded30關閉13.349s且worker0；完整盤勢正常完成另以Native探針驗，peakRSS1.452GB不與提前取消0.675GB混報。30列高亮p95 49.65ms不代表全互動速度。

Market61、root loader9（8項重跑）、整合47、Workbench85、validator25／4skip、mypy766、13檔compile通過；唯一Windows fixture長路徑失敗保留，短新Temp重跑1pass。5＋1 Native場景12個launcher／Python PID觀測均退出。來源與資源邊界、code／summary SHA與原始收據見[階段1收據](PRODUCT_STAGE1_PERFORMANCE_IMPROVEMENT_20261005.md)，commit readback留output。原plan append-only，UX01→UX16/17→UX18/19→UX04/05依賴維持。階段1／UX17仍部分完成：早期breadth／relative SQL僅區段前後取消，來源availability／warm-up／PIT／universe／benchmark與自然ML資格未全部完成；不新增方法或UX18 Gate。

1477既有Native驗收不重開，1000×835／125%接受與1000×800限制維持；沒有writer／訓練／永久刪除／push，未知paper檔及C:/ta_iso_1005映射未動。本地commit/blob/status驗證後停止交父層。


## 2026-10-05 階段1早期SQL取消小包

基於2acdbe2c，四檔backend補Builder→Breadth／Relative service→provider→shared loader取消callback，獨立SQLite分支亦用連線專屬progress handler；SQL確實中止才轉取消例外，真實DB故障不遮蔽，舊provider／Series.map dtype／Decimal／cutoff／排名不改。47 focused、50 UI/Shutdown整合、mypy766及7檔compile通過。Native早期SELECT中關閉：worker仍running時視窗保留，32.77ms至native-finished、131.31ms至hidden、沒有完成snapshot／殘留worker；取消→同來源按鈕重試21.141s正常產生真實snapshot。3個Native場景6個launcher／Python PID全退出，input guard／來源rowset SHA不變。

最終單跑loaded30首屏9.350s、p95 54.173ms、peakRSS618,389,504 bytes、全程13.421s退出；這是spot check，不替換舊5跑median。五跑凍結gate逐項核對：首屏-14.84%、四筆純啟動RSS-18.19%、loaded30+close峰值-57.00%（含提前取消）、p95 49.65<300ms皆通過；Industry42.56%通過20%，Backtest18.62%未達20%（原凍結是兩段各自20%，已更正文案，不放寬或微調湊數）。上包13.349s是全程序時間而非close latency，PID退出證實不是只藏UI。完整normal retry RSS1,456,594,944 bytes與提前取消分列。

詳見[取消與gate收據](PRODUCT_STAGE1_SQL_CANCELLATION_20261005.md)與output/qa/product_stage01_20261005/stage1_sql_verified.json。main／view／原初始化優化／profiler的未變blob已核對，舊數字保持其版本身份。沒有重跑五baseline／訓練／producer／大DBcopy／永久清理／push；未知paper檔與C:/ta_iso_1005映射未動。停止交父層。

下一原plan包是stage1／UX02純呈現共用狀態字典，先接Research Console／Backtest，沿用上下文列與分層元件，保留未知碼、狀態維度及結果身份；本包只盤點，未實作。UX16來源能力、UX19容量／writer依賴與自然ML資格分開，不拿自然成熟阻擋UX17／UX02工程。不宣告整個stage1／UX17或全部gate完成，也不盲跳UX18／新ML。


## 2026-10-05 UX02 共用狀態有限切片

`ui_qt/status_vocabulary.py` 提供純呈現 `status_label`／`status_detail`，明確區分 data／load／research／qualification／event／validation；未知碼保留，completed 不跨維度授予資格。盤勢、持倉系統健康、選股、個股及 Console 的既有入口共用詞彙；Workbench 將時間等待／休市與具名故障分開，回測保留 PASS／WARN／FAIL 並加白話驗證狀態。原始診斷、來源及日期／身份沿原 DTO 保留，沒有修改策略／producer／模型或拒絕 guards。

本包是 UX02 有限落點，非全頁狀態重構或整個階段1完成。Backtest 初始化18.62%仍未達20%凍結門檻；UX16來源／PIT及UX19 writer／容量依賴另列，不以自然成熟阻擋本包工程。詳見 [UX02驗證收據](../06_qa/UX02_SHARED_STATUS_VOCABULARY_20261005.md)。未重跑效能／learner／Native1477、未producer／清理／push，未知根檔及C:/ta_iso_1005還原映射未動。完成本地commit／blob核驗後停止交父層。
