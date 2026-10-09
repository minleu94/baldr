# Baldr 產品補完開發交接（2026-10-09）

## 狀態與範圍

使用者要求先記錄進度並保存工作區，再開新對話續接。產品開發目前暫停；本次 commit 是本機 dev 的 WIP 交接 checkpoint，不是發布、完整驗收或新 EXE。完整補完範圍仍為 P00–P14、M1–M3、F01–F23，不能縮成目前幾個通過的子項。讀取 AGENTS.md 與 Scoped SSOT 後，以本文件、現行原碼及各項 root review 接續。

使用者最後實測 d9a115f67d2b：推薦理由雖變大，分數、門檻及可能影響排名因素仍看不全；H20 單股證據約 20 秒，結果解讀及完整下鑽仍不足。不得把舊 EXE 當成後续原碼修正的人驗結果。

## 開發進度與下一步

| 工作 | 已有證據／界線 | 下一步 |
|---|---|---|
| 推薦理由可讀性 | 396c08e8 的原碼修正已有 11 個版面測試（含 460×700、End/PageDown）；尚無新版人驗 | 依 BALDR_RECOMMENDATION_SCROLL_CURRENT_REVIEW_20261009.md 核對目前完整內容捲動與排名因素，再安排新版驗收 |
| P01 千檔效能 | proof rehydration 55086ec4、lexical memo f9ead461、component tuple memo 30812082；最新 5 cold + 1 warm 固定矩陣：翻頁 p95 239.4695ms 通過、篩選 1074.3634ms 失敗、排序 344.7445ms 失敗（門檻 300ms）；清理及來源不變檢查通過 | 先完成 CPU／memo budget 診斷並審查新候選，通過定向回歸後才跑一次新矩陣；不可調高門檻、縮減資料或以預熱冒充 cold |
| F02 MA 完整合成旅程 | V11 唯一 attempt exit 0、78.984 秒；AND 59、OR 158、OR-only 97，Watchlist 可見實際單擊／雙擊 typed=1、generic=0，清理 jobs=0 | 僅接受固定合成來源完整旅程；不等於原資料、新 EXE 或真人驗收。不要重跑相同 V11 |
| F12 營收主程式整合 | reader／index／獨立 UI 已有局部證據；Main C candidate 原碼及 54 code + 4 guard dependencies pins 已檢視 | C candidate focused 真 Qt、lifecycle、路徑負例測試尚未完成接受；先測試、凍結、root review，才授權一次完整 Main 新 process；目前沒有完整 native grant |
| H20 config/source-port | M native08 exit 0，僅接受 config、preverified port、資源清理；guard 內 actual fixed reader invocations=0 | 真正 read_pinned_json + 固定 source-port 的 initial／terminal 各一次 guarded read 尚缺正例。新窄封套先證明角色及 phase 正負例，不可替換 reader；尚未授權 public pipeline/Main |
| F03 KDJ／多父群組 | 尚有 MA-only reader 與群組 publication identity 不相容 | 依 BALDR_F03_MULTI_PARENT_GROUP_PUBLICATION_PLAN_20261009.md 實作共同原子資格；不得直接放寬 identity 或部分發布 |
| F06 波動證據 | ATR14/SMA30 與 regime window20 的方法語意未對齊，尚無合格證據 | 依 BALDR_F06_VOLATILITY_EVIDENCE_PLAN_20261009.md 先建立 Decimal、來源與方法合約；不得宣稱完成收斂 |
| 其餘補完 | BALDR_COMPLETION_GAP_REVIEW_20261008.md 為缺口對照入口 | 維持完整 P/M/F 清單，逐項更新驗收證據，不以局部通過標整體完成 |

P01 最新 QA：`output/qa/p01_1000_component_tuple_memo_candidate_20261009_a/`，看 `matrix_aggregate_final.json`。strict renderer profile 5921 次與 memo render 11102 次不是同一數字；第一次純 CPU 診斷 strict676/render-only581 未重現 profile，第二次 path-count 失敗；budget sweep 尚未產出。不要用合成深路徑機制示範代替真負載證據。

F02 QA：`output/qa/f02_ma_normal_ui_fresh_pid_20261009_v11_watchlist_route_and_click/run_attempt_ffce90498c624514a7f3f1874b89e644/`。F12 QA：`output/qa/f12_main_revenue_new_pid_20261009_c/`。H20 QA：`output/qa/h20_h9_public_cohort_pipeline_candidate_20261009_m/`；native01–07 失敗證據保留，native08 不代表 guarded 真讀取合格。H20 frozen source 在 `output/qa/h20src09/snapshots/s3/source`，H9 fixture 在 `C:/t/h20dual_main_integration_candidate_20261009_h9`。

原保存 2382 H20 為 **684bp（+6.84%）、20 個交易日、未扣成本**，決策日 2026-10-07、來源日 10-06、特徵截至 10-05，成熟 outcome 未提供。合成 1234bp 不得替代原保存估計。2382 被篩掉的 -31.229…% 與 +50% 門檻只說明未入選，不能代替完整個股研究。研究估計不等於 Advice、勝率、權重或買賣指令。

## 協作與續接限制

bootstrap_identity、h20_summary、universe_run 已隨使用者要求暫停。新對話獲續接指令後可重新分派互不相依的子任務，root 負責整合及證據審查；不要把已失敗／未跑／局部通過混為完整驗收。使用者要求多用平行 subagent；原分工使用 Luna Max，須確認新對話可用模型再安排。

本次工作區還包含其他 agent 的排程、paper、ML、來源與文件整理修改，依使用者授權一併保存；本 checkpoint 不宣稱 root 已對所有修改執行完整回歸。不得覆寫其他 agent 的成果，亦不得停止他們獨立負責的正式排程。當前補完測試授權是隔離 1,000 檔合成資料、產製器及封套；不包含修改原始 D 槽資料、正式排程、實盤或訓練。

## 儲存封存與本機排除

兩批搬移已完成：6 + 28 個原目錄，完整 SHA-256 核驗後移除 C 原副本並建立 Junction；E 副本及回滾清單保留。共 184.62 GiB 邏輯內容，各批操作期間觀測差合計約 122.75 GiB（不是整段淨釋放量）；未量測實體配置，不能把差額直接解釋成壓縮。D 正式資料與 E 舊封存未改動。

- `docs/03_data/C_DRIVE_QA_COLD_ARCHIVE_20261009.md`
- `docs/03_data/C_DRIVE_QA_COLD_ARCHIVE_BATCH2_20261009.md`
- `docs/06_qa/C_DRIVE_QA_COLD_ARCHIVE_RECONCILIATION_20261009.md`
- `docs/03_data/STORAGE_ASSET_REGISTER_20261006.md`

E 根目錄分別為 `E:/FA_Data_ColdArchive/baldr_c_drive_archive_20261009`、`E:/FA_Data_ColdArchive/baldr_c_drive_archive_20261009_batch2_plain`。`output/qa/integration_20261002` 因內部 Junction 測試案例留在 C。嚴格拒絕連結的歷史測試要先還原普通目錄；不要把經 Junction 的來源直接送入嚴格 reader。目前正式版、回退版、d9a115f67d2b 保留。

Git 不提交 QA raw、暫存、封套、EXE、資料庫。根目錄六個殘留檔仍原地保留：presenter.py、reason_engine.py、recommendation_service.py、supervise_f02_ma_composite_257.py、test_r019_reason_regime_parity.py、test_recommendation_view_presenter.py；完整備份在 `output/qa/root_residual_backup_20261009_b/inventory.json`，後三份相關 diff 仍需正式清理審查。它們不是正式模組的新位置，不能導入或刪掉來假裝清理完成。

本次以本機 `.git/info/exclude` 排除上述六檔、已識別 QA 暫存與 `scripts/maintenance/` 內本機一次性封存工具，檔案不刪除、不搬移；Git clean 不代表磁碟沒有暫存。這些本機工具與 QA 證據不會隨 clone 搬移，後續仍需依本機封套及 E 收據復原。

graphify query 本次因 uv trampoline canonicalize script path 失敗；既有 graph 只作定位，實際來源及現行證據優先。不要為本次交接重建 graph 或重跑千檔產製。

## 文檔 agent 可處理的範圍

本機 checkpoint 保存後，可解除因本對話開發而暫緩的文檔整理：Snapshot、Index、README、Manual、Roadmap／架構導覽與歷史歸檔連結，可依 Scoped SSOT 整理；本文件與各 root review 的驗收界線必須保留。原始 QA 收據、失敗記錄、封存清單及 SHA 不可改写。未驗收項目不得改成完成。新開發對話如又開始修改相同文件，雙方先核對 git diff／最新 HEAD，避免覆寫。

本 checkpoint 的驗證採 Git diff whitespace 與 Python 語法檢查；未執行完整 UI、mypy、正式排程或全產品回歸。最終 commit SHA 與驗證結果由交付訊息提供。

### 本次 checkpoint 驗證結果

59 份 Python 的 AST 語法檢查通過。staged diff --check 發現 12 份既有／新來源或歷史封存文件的檔尾額外空白行；為保存原工作與歷史內容，未改寫這些檔案。忽略 blank-at-eof 後另查實質 whitespace 錯誤；此檢查不代表功能驗收。
