# B04 選股來源與收藏查看狀態限定交付（2026-10-06）

本文件是 lane QA／整合交接，不取代唯一主 plan `output/plans/baldr_product_experience_plan_20261004.md`。原七個有限 closed、性能例外、全局 stage／UX 狀態均不重開、不升格。

## 基準與 ownership

- 固定 base：`ba4e9e59da7946aa66fd5eac3729e091dfe5cced`。
- branch：`lane/baldr-b04-selection-watchlist-20261006`。
- worktree：`C:/Projects/PythonProjects/technical_analysis/output/worktrees/baldr-b04-selection-watchlist`。
- 唯一 dev 整合 owner：`01a11020-88c2-7506-acc3-d51ecb674032`；本 lane 只作本機 commit，不 cherry-pick dev／push。
- 變更限三個指定 view、`test_ui_qt_recommendation_layout.py`、新增 B04 tests 與本 QA。原 Manual、plan、main、config、DTO、codec、chart、storage 均未改。
- 執行角色沿 repo Execution／QA／Documentation 規範。Team shared state 被本次排他 ownership 限制覆蓋；沒有共享檔寫入。graphify 2026-09-29 舊圖只用作定位，API 以固定 base 原碼核對。

## 可 review 的行為

1. 推薦既有第一個來源 tab 保留。按「讀取可用來源」明示背景呼叫原 `RecommendationExecutionQueries.list()`；僅列出目前 `_canonical_loaded_result_identity()` 接受的 completed canonical execution。舊 schema／legacy／缺件不補資格、不自動挑 latest。查詢索引失敗時保留原選項／原結果，不繞過 backend 完整性守衛。
2. 選項顯示原名稱、決策日、保存日期及 result ID。完整八欄身份作為選項資料；Qt QVariant 的 list 轉換先驗證形狀再還原 tuple。日常入口不要求手填 ID；舊隱藏 input／單筆方法 ABI 保留。
3. 按「讀取」沿原 `get(result_id)` 與既有 canonical renderer。回讀 hash／schema／artifact／保存時鐘任一與選取身份不符就拒絕替換；不是把同 ID 的新版本默默當原來源。取消增加 generation、合作取消 worker；晚到回應不能換 last-good。
4. 有推薦項的來源標為「保存推薦」，零推薦項標為「保存篩選／空結果（非推薦）」。每日研究條件沿原第二個 tab、原 MA20／MA60 方法與 AND／OR，與保存推薦分開；未等待 B11，不造新方法或 producer。
5. Personal capture 與 Stage C 評估控制預設收合，明確按「個人模型擷取與評估（進階）」才能展開。刷新／回讀不重設使用者的展開選擇；原 callback、檔案選擇、來源守衛不變。
6. 每日研究增加股票代碼局部搜尋，只在目前 `_all_rows` 範圍取列。完整符合／未符合／未知分母、來源 manifest、完整 cohort 與 saved query/context 均保持原值。局部顯示數量另列；返回仍要求原 manifest，被目前 filter 隱藏的股票不強制改 filter，清除 filter 後可精確定位。
7. 候選池直接顯示原 notes 收藏理由；缺理由明示未提供，不把推薦理由冒稱個人理由。較前變化目前 DTO 沒有同源比較欄位，明示未知、不借新行情、不造百分比。
8. 「已確認查看／稍後查看」是**僅本次視窗**的私人查看狀態，畫面明示「不保存、不排程提醒」。key 綁完整來源列，涵蓋 stock、added time、source、result、decision、pins、decision identity、bookmark、notes；同股不同版本互不串用。沒有呼叫 writer、改 notes、改 bookmark、改 evidence 或金融計算。

## 驗證與真失敗

全部 Qt 使用 offscreen；所有新保存只在 synthetic fixture root。沒有開 Native、正式資料／Task／ACL／migration／清理／訓練／交易。讀取時沒有發布或更新快照。

命令共用 Python：`C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe`；cwd 為本 lane worktree；`QT_QPA_PLATFORM=offscreen`、`PYTHONIOENCODING=utf-8`。

| 命令／案例 | 真結果與邊界 |
| --- | --- |
| `-m pytest tests/test_baldr_b04_selection_watchlist.py tests/test_ui_qt_recommendation_layout.py tests/test_ui_qt_watchlist_layout.py tests/test_ux04_05_daily_market_research_view.py --basetemp=C:/Projects/PythonProjects/technical_analysis/output/qa/b04-final-20261006-run02 -q -o addopts= -p no:cacheprovider` | 19 passed。含原三組 10 案與新增 9 案；不把重跑相加。 |
| `tests/test_ui_qt_personal_recommendation_choice.py -k 'saved_result_load or restored_saved'`，其餘同 `-q -o addopts= -p no:cacheprovider` | 7 passed／22 deselected；原拒絕／過期／取消 ABI 保留。 |
| `tests/test_ux03_research_bookmark_ui.py tests/test_rank_research_bookmark_flow.py tests/test_watchlist_stock_analysis_navigation.py tests/test_watchlist_empty_pool_presentation.py tests/test_ui_qt_recommendation_execution.py`，其餘同 pytest 選項 | 初跑 69 passed／6 failed。六案均因 default Temp 的 `C:/Users/archi` ancestor `CreateFileW errno5`，原 no-follow root 守衛 fail closed；沒有改 guard。 |
| 上述兩檔的六個失敗 node，`-k 'saved_analysis_reads_exact_source_and_rejects_future_without_writing or explicit_same_stock_screening_source_is_bound_as_exclusion_and_survives_reopen or saved_source_data_date_must_not_exceed_query_cutoff or saved_market_date_after_source_decision_stays_rejected_for_later_query or screening_only_execution_saves_reopens_and_researches_exact_stock or saved_empty_canonical_execution_load_keeps_identity_and_date' --basetemp=C:/Projects/PythonProjects/technical_analysis/output/qa/b04-store-20261006-run01` | 6 passed／50 deselected。repo 內新 synthetic root 解決 ancestor sandbox 限制；不宣稱深 Unicode COW 接受，不重跑 B02。 |
| `-m mypy ui_qt/views/recommendation_view.py ui_qt/views/watchlist_view.py ui_qt/views/daily_market_research_view.py --follow-imports=silent` | Success，3 source files；不是全 roots mypy。 |
| `-m py_compile` 三 view 與兩個 changed tests | exit 0。 |
| `git diff --check` | exit 0，只有工作副本 LF→CRLF 提示。 |

新案例核 saved option→原 query get→股票 context 的原 result／stock／decision date，synthetic 真 store 的檔案集合與每檔 SHA256 前後相同；另核修訂拒絕、list/get 取消、晚到 callback、未知／不支援來源、局部 filter／完整分母／返回、同股版本查看狀態隔離、無 evidence 寫入。

初版新測試曾因 QVariant tuple→list 使選項未帶入 ID，已修正產品轉換而保留 identity assert；另新增真 store 測試誤把既有 `ResearchStockContextDTO` 當 dict，改為原 typed attribute assert，未刪 identity／日期／檔案 pin assert。展開評估的 layout 測試需要展開後重新捲至新 maximum；保留控制可見／五列／完整幾何 assert。失敗不冒稱 pass。

重型 UI gates（mandatory Workbench、update validator、全 roots mypy）依本次委派由中央在穩定 union 跑一次；本 lane 未跑、不冒稱整鏈或 Native／真人已完成。

## 中央 Manual 精確 patch 建議（只提案，未改共享文件）

在 Manual「第一版有限研究流程與驗證入口」第 1 步之後補：

> 「已保存推薦／策略研究」按「讀取可用來源」，先選同名結果的決策日與保存日期，再按「讀取」。不需輸入 result ID；保存篩選／空結果會明示非推薦。讀回來源版本不符時保留原結果，重讀選項後自行選擇；取消／晚到回應不取代原結果。每日研究條件仍屬獨立研究來源。

在 Personal capture／Stage C 操作段補：

> 「個人模型擷取與評估（進階）」預設收合；展開後沿原明確 capture／summary 選擇，不搜尋 latest、不提高模型資格。

在候選池與每日研究 filter 段補：

> 股票代碼搜尋只改目前核驗列表的可見列；完整母體與未知分母保留。返回來源仍核對原股票與 manifest，清除局部搜尋才能顯示被隱藏列。收藏理由顯示原個人備註；未提供或比較資料不足保持未知。「已確認查看／稍後查看」僅於本次視窗保留，關閉不保存、不排程提醒，不改 evidence。

Coverage：Manual 必須同步以上入口／步驟／判讀／限制／來源失配排錯；Snapshot／routing／coverage／index 由中央按實際接受範圍更新。產品方向、6M 與成熟度無變動。

## 明確未完成與接線提案

- 個人理由編輯、跨程序確認／稍後、實際提醒／變化比較仍未完成。現有 `WatchlistService.get_stocks()` 只讀 notes；`add_stocks()` 會跳過 duplicate，沒有合格的原子 annotation update 公開 API。不能用 remove/add、private `_save_watchlist()` 或 notes 拼 JSON 繞過 revision／identity。
- 後續需 storage owner 在既有 Watchlist store 提供原子 `update_observation_annotation(*, watchlist_id, item_identity, expected_revision, reason, review_state)` 與 `read_observation_annotation(...)`；state 固定 `pending/confirmed/later`，精確 key 應用原 `DecisionIdentity`／bookmark 身份及 store item selector，拒未知／衝突／修訂；只改私人 annotation，禁止改 source pins／bookmark query／推薦／evidence。既有 model／repository／codec 如何表示該欄位由其 owner 凍結，本 lane 不造平行庫或 shared DTO。
- 公開 API 凍結後，B04 的 `WatchlistView._set_observation_state()` 改接 exact annotation update，`_render_observation()` 改唯讀 projection；未完成前畫面必須保持本次視窗限制。此為精確 caller 接點提案，不是已實作 API。
- 比較變化需 backend 提供同 stock／來源 scope／decision／data date 的具名 comparison DTO；本 lane 不從今日或任意版本相減。未知保留 unknown。
- 原 query `list()` 仍按既有 backend 完整性語義核驗來源；沒有引入新分頁或歷史索引、也不宣稱大規模保存來源性能接受。

## 回滾清單

| 檔案 | 類型 | 回滾方式 | 風險 |
| --- | --- | --- | --- |
| `ui_qt/views/recommendation_view.py` | 修改 | 整合 owner 單獨 revert lane commit | 返回原手填 ID／展開評估行為；不改保存資料。 |
| `ui_qt/views/watchlist_view.py` | 修改 | 同上 | 移除本次視窗查看狀態，原收藏／notes 不變。 |
| `ui_qt/views/daily_market_research_view.py` | 修改 | 同上 | 移除局部代碼搜尋；原 saved query 與完整名單保留。 |
| `tests/test_ui_qt_recommendation_layout.py` | 修改 | 同上 | 恢復原評估控制幾何檢查方式。 |
| `tests/test_baldr_b04_selection_watchlist.py`、本 QA | 新增 | 同上 | 移除本 lane 驗證與交接說明，無 production dependency。 |

回滾前確認整合 tree 沒有覆寫這些檔案的其他未提交工作；只回退本 lane commit，不 reset dev，不動 QA synthetic artifacts 或正式資料；再跑受影響 focused tests。完整 commit hash／changed blobs 由交付訊息提供，避免文件記錄自身 hash 形成循環。
