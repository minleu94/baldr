# 最小續接清單（2026-10-05，Batch9）

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
