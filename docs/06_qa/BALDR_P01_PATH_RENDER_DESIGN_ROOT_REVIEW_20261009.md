# P01 路徑字串重用設計審查

Root 於 2026-10-09 讀取一頁設計與目前 `personal_data_paths.py` 後，允許進入受控實作；本文件不代表實作、效能或整體產品驗收已通過。

## 允許的實作

- 僅在個別 `read_selection_page` 操作內重用已通過既有字面檢查的路徑所對應的 I/O 字串。
- 正式接點限於 `app_module/personal_data_paths.py` 與 `app_module/daily_market_technical_universe_v4_query.py`，另補對應測試及 QA 摘要。
- 每次操作使用新的有界 memo，成功、例外及取消均在 `finally` 釋放；巢狀操作獨立。
- 不改金融數值、PIT、selection、排序或資料資格，不跳過任何 lstat、reparse、身分、完整 bytes/SHA、layout 或 cancellation 檢查。

## 審查要求的修正

1. WindowsPath 的 equality 可折疊大小寫，不能直接以 Path 作 memo key。key 必須保留 exact platform type 及精確 lexical spelling，驗證不同字面輸入仍得到各自 strict converter 的結果。
2. ContextVar 可被同一 context 內的普通 strict API 與回呼繼承。「沒有建立 scope」不足以證明「沒有借用 scope」。必須明確實作並測試 strict API、巢狀與重入回呼的隔離。
3. 容量耗盡必須回到 strict conversion，不能拒絕合法頁面或減少檔案核驗。測試須比較 DTO/identity 以及檔案核驗事件順序與次數，並涵蓋 selected/unselected tamper 復原 mtime、reparse、取消和例外清理。

## 下一個驗收

先審實際 diff、scoped tests、mypy/compile 與來源 pins，再使用原固定 1,000 檔、五 cold／一 warm、每類 30 samples、嚴格小於 300 ms 的矩陣。既有 proof-rehydration 矩陣翻頁與排序通過，篩選 p95 677.9689 ms 未通過；純 lexical probe 與 cProfile 不能替代該門檻。

目前不要求使用者真人重測；完整 Main 收藏重開及 H20 載入驗證、可交付 EXE 仍未完成。

## Root 既有公開路徑相容性回歸

Root 讀取 WIP source 後補要求 absolute Path eligibility 與 creating-thread 限制，owner 已接入。以下測試期間 owner 暫停兩個正式 source 編輯；測試所用 SHA 為 paths `d90a46bcd9a83bd905262765dbf2718bf29f0e324bda6bf6573b2a7b887cf1ed`、universe query `ca4c84ac91d1329f3b05eec576a32bb5d587566ab25ba93cb0e9f4c9c4dea515`。

Root 實際執行既有 `tests/test_personal_data_paths.py`，僅使用 synthetic fixtures：

- 沙箱 attempt terminal exit 1：84 passed、23 failed、7 skipped，20.51 秒。存在 WinError 5 hardlink/rename 與長路徑／COW preflight 環境症狀；不當作相容性通過。
- 全新原生隔離根 `C:/t/root_paths_regression_20261009_a_63f17b`：113 passed、1 failed，35.08 秒。唯一失敗是 `test_deep_unicode_control_hardlinks_rejected[rollback]` 的測試前提 `len(str(target)) > 260`，實際 258，尚未觸及產品拒絕判斷。
- 新的較長隔離根 `C:/t/root_paths_regression_20261009_b_longfixture_72d91c`，僅重跑該 rollback case：1 passed，0.41 秒，exit 0。

原生 raw logs 及沙箱摘要保存於 `output/qa/root_personal_paths_regression_20261009_a/`。所有 114 cases 各有成功證據，但不是單次 114 全綠；原失敗不得刪除或改寫。這項回歸不代表新增 memo 的 isolation/equality/tamper tests 通過，也不代表效能或 Main 旅程完成。測試結束已解除 owner 的 source 暫停，可繼續定向測試與實作。

## 新增七項定向測試

Root 直接讀取 `output/qa/p01_page_path_render_20261009_b/attempt03_native_frozen.log`：7 passed、11 deselected，26.72 秒。log SHA256 `f23ce8f2097eb01b9fac7b3701504a4b4718eb635fdf11d1b9d246be414fe040`；兩個 source SHA 與上段相同，test SHA256 `10f002b52b00b10ceb114a592468b348227a882f6e3e146abbf9d209e7a3eb85`，Root 已獨立重算。

已實讀新增 tests，涵蓋精確大小寫字面 key／copy-context 跨執行緒 fallback、相對及 tilde Path 不快取、entry/byte budget fallback、巢狀清理、完整 page/query payload 及 fresh I/O event 順序相等、callback direct strict read 隔離與巢狀 page、讀取中取消清空、selected/unselected bytes tamper 復原 mtime 仍拒絕、真正 junction 拒絕與 fixture 還原。測試曾因 wrapper 無 to_dict、長路徑測試 I/O、例外 message/code 比較及 junction ancestor／cmd argv 出錯，均只修測試，原失敗與 skip 保留。

目前允許繼續 scoped mypy/compile 與既有 proof/session 回歸，尚未認可完整來源整合、效能門檻、Main 旅程或 EXE。不能將七項測試結果替代原固定 1,000 檔矩陣。

## 既有回歸終態核對

Root 直接讀取 `attempt01_regression37_native.log`：37 passed、5 deselected，420.34 秒。實際範圍是 query 13、session metadata 18、指定 read-session 6；不包含 semantic rehydration，不能沿用先前另一組 37 的範圍說明。

缺少的完整 semantic rehydration 檔另行執行；Root 直接讀取 `semantic_rehydration13_native.log`：13 passed，19.92 秒。兩份 log 均位於 `output/qa/p01_page_path_render_20261009_b/`。Root 再讀正式來源 diff，確認快取只保存單次操作內的路徑字串，strict clone 與外部取消回呼暫停 context，finally 清除；沒有加入檔案資格或內容快取。scoped static 收據與來源凍結仍須核對，效能矩陣與完整 Main 驗收仍未完成。

## 來源接受與下一固定候選

Root 獨立 scoped mypy 終態 exit 0，兩個來源無問題；已讀 owned test 全部 diff、來源 pins 與回歸 logs。本輪四個檔案保存至本機 dev `f9ead4618910b4357ecf51a3bc0161d2ea144ed5`，僅接受契約相容性，不代表速度門檻、Main 或發布通過。

下一矩陣候選位於 `output/qa/p01_1000_page_path_render_candidate_20261009_a/`。Root 實讀 builder 對上一版本 diff，保留固定 d12 archive 與完整 inventory／bytes 驗證，明示 repository、feature、query、paths 四個 overlays；不從 dirty HEAD 重建。已允許一次全新 `C:/t/p01prhmemo09` 候選建樹，僅複製固定來源，不執行 producer 或 benchmark。矩陣仍須待 manifest、純契約與固定資料封套審查；原 sealed store 不變。

候選建樹已完成。Root 獨立遍歷全樹，重算每個檔案 SHA／size／相對位置並與 manifest 逐項比對，終態 exit 0：4,465 檔、80,223,277 bytes、零 pyc，全部一致。manifest SHA256 `3c90ea2d845176b5b1e0bbd95704f2d8144b3a562b14b0b1496bf714694d3fb4`；build receipt SHA256 `79cfb319b74b27395d66b76d44e26867275c3ba9ddb8d25c4b7de832040484cf`。本輪 matrix manifest builder 尚待移除舊 v2 路徑與 pins，再作純契約；不得先執行舊入口後將失敗歸因產品。

Root 後續實讀 controller／manifest builder 對上一版 diff，發現 builder 尚保留 overlay count 3 與 three 描述，要求在執行前修正；已再讀確認改為 4。新 manifest 已產出，維持五 cold／一 warm、三類各 30 samples、300,000,000 ns 門檻、原測量邊界與取消形狀，沒有縮小母體或變更操作。controller 變更限固定 metadata／pins／schema／bytes；仍待純契約終態及完整凍結封套審查，尚未執行效能矩陣。

Root 實讀純契約終態 log：24 passed，1.75 秒；測試包含 schedule、query/source identity 篡改、typed empty page、PID/create-time replay、完整 warm events、固定原 store 與四 overlays、manifest 可重建及 aggregator 窄差異。獨立重算 controller `8fe65d920a388a0362a72c43b67c716bd038e4c9e64e96cfbaa4f8f2c5f21617`、aggregator `55fba6df2f9081e7cb6f243b6c1d4883f551e16dea1405ede65bb55247193943`、candidate manifest `90ed7af39fec5afa442c49d86526362e12e78b3b404aaa018c7b5d44d58865fd`，與 receipt 一致。已允許一次 static preflight，禁產品模組 import、SQL、network 或 worker；尚未授權六角色 native。封套的 cache disabled 指原 benchmark cache prototype，不能解讀為受測來源沒有本輪 lexical memo。

Static `f73a7458c4a6` 終態 exit 0，Root 實讀原始 receipt：來源與 sealed store 起訖相等，無產品 import、SQL、network、subprocess 或 worker。已授權完整六角色矩陣各一次，依序執行、失敗保留並停止。cold_01 `C:/t/p01cur_rd_e068a7ed83` 已終態 exit 0；Root 實讀 child 與 supervisor 收據，20 頁完整讀回 1,000 檔、全域順序 digest 與既有固定 selection 相等、S00256 跨 segment 身分一致、guard counters 零、來源／store postflight 不變、Job 清空。這是一個 cold role 的成功，尚不足以判定 p95 或整體效能通過。

## 下一組件重用切片

本輪六角色與 90 samples 完成後，Root 獨立重算三類 p95：174.3009／525.9606／219.2445 ms，篩選仍失敗。已有 filter profile 顯示條件建立／選取只佔少量工作，主要時間落在 26 個 child references 的頁面 materialization。下一切片只重用 `reversed((path, *path.parents))` 所產生的不可變組件 tuple，接點限 paths 與 repository；Root 已實讀兩處目前都逐次重建鏈。

所有組件仍逐次 lstat／reparse，次數與順序必須等於 strict；不快取檔案資格。memo 的總 entry／UTF-16 byte budget 必須計入 tuple 每個 lexical path，且維持 exact type／spelling、absolute、同 thread、外部 callback／strict clone 隔離與 finally 清除。V10 Main 已終態並清理，允許 owner 依前像套用窄 diff；V11 QA 先準備，不與修改中的來源同時執行。這不是新效能通過證據。

Root 已讀第一版正式兩來源 diff：58 additions／6 deletions，兩處 link guard 仍執行原 lstat／reparse，只更換組件產生方式。Root 另以合成字面 `C:/synthetic/Case/leaf` 執行純 helper 探針，exit 0：組件順序與原 tuple 相等、同一 scope 重用 tuple identity、render／components 共同兩 entries 的 UTF-16 預算精確為 240 bytes、finally 兩份字典清空。此探針沒有檔案 I/O，不代替 tamper／junction／取消與完整事件等價測試；第一版仍待 owner 凍結。

### Component tuple 正式來源審核

Root 實讀兩產品來源完整 diff、新測試、既有 callback/cancel 增補與原始輸出，並重新計算產品 SHA：personal_data_paths=`1f08d1b4f92a1a002192b09a7d92cc37a58fdba2c5f2d668158cd357f5bc2912`；snapshot repository=`1e494ac97ee72ad05b9cb609b62bc9f39bfb0c2b3341634724189d2db1168f59`。實作保留逐 component lstat 與 reparse 判斷、fresh bytes/hash，不重用檔案狀態；共同 entry/UTF-16 字串預算、thread 邊界與 finally 清理成立。金融計算、PIT 特徵及篩選結果邏輯未變。

原始 owned_tests_native_attempt02.log 為 10 passed；query_regression_attempt04.log 為 7 passed，包含 callback strict read、取消、selected/unselected mtime-restored tamper 與 fresh I/O 序列。後續只修改 junction 測試的隔離路徑檢查，junction_containment_attempt01.log 為 1 passed；不可稱最後 test bytes 已一次跑過全部十項。兩來源 scoped mypy clean、四檔 compile pass；Root diff --check 無錯。

Root 接受上述兩產品來源凍結，用於 V11 source pin 更新與新的固定效能候選準備。最終測試與文檔 pins 仍由 owner 對齊；尚未 commit、尚未授權新矩陣或完整 Main。此前 filter p95=525.9606 ms 的失敗結果保持有效，不以單元測試替代效能驗收。

### Component tuple 固定效能候選樹審查

Root 已獨立 rglob 並重新計算候選 `C:/t/p01prhcomp10/technical_analysis` 全部 4,465 個檔案的相對位置、size、SHA，與 source manifest 完全一致：80,225,544 bytes、0 mismatch。來源 manifest=`f0e639465f70f321cdd5372c68c4e688b4d7b60fee8c33ecc3d35416f508cb10`，inventory=`b3bf814085bfef4da13b05492e2867d5e7981d9d6c064720be4c21fbc6a4dca4`。四 overlays 為 repo1e494、feature844、queryCA4、paths1f08；沿用固定 d12 archive 與原 sealed 1,000-stock store，不從 dirty HEAD 重封存。

Root 已直接讀 controller、aggregator、manifest builder 與 contract test 的 exact diffs；變更只為候選 metadata／pin／four-overlay binding，原方法、guard、操作與統計條件未改。pure_matrix_contract_attempt01.log 為 24 passed／2.01 秒；僅接受契約，不代表實際效能。candidate manifest=`e17582a47284d529a8d43d8d2ad4e2cda88b072f19e787223318d667ee67e984`、controller=`cdb8e14df9823c2496bde9b8e2b1ffc232c3872267bad74b4be5237a6be40155`。仍待 static preflight 的實際來源／store 前後核驗與零副作用證據，尚未授權新六角色矩陣。

### Component tuple 靜態預檢接受與矩陣授權

Root 已直接讀 `static_preflight_c2099d92fb75.json` 與 log：failures空，source/store 起訖完全相同，SQL/network/subprocess attempt皆0，未import產品、未呼叫producer/opener、未啟worker。接受靜態scope。已授權owner確認同一static handle terminal0後執行一次固定6roles矩陣，使用candidate e17582…e984/controller cdb8e…0155，維持5cold1warm、每類30／共90 samples、原300ms門檻、原deadline與sealed store。每role新attempt、failurestop不重跑、不預暖、原aggregator，不改來源資格或統計。尚未取得任何新performance結論。

### Component tuple cold_01 實際收據核對

Root 已直接讀 `C:/t/p01cur_rd_71ce1b5978/supervisor_result.json` 與 child_result.json，並以 Python equality 確認 source_and_store 起訖完全相同。Child passed，20頁×50列共1000檔、首S00000末S00999、ordered digest661355…b86、跨段S00256 page5 offset6符合原固定契約。Supervisor failures空、timeout=false、child wait0、Job PID清空、cleanup completed；parent唯一 subprocess attempt 是已核准launch1，network0。第一頁read為186174600ns，但這是一輪cold樣本，不能視為p95或完整效能接受。Owner按既有授權接續cold_02，Root不重啟或重複輪詢其handle。

### Component tuple cold_02／03 核對

Root 直接讀 `C:/t/p01cur_rd_00dffb13ab` 與 `C:/t/p01cur_rd_ffca3e2e0d` 的 supervisor/child JSON，以程式斷言 source/store相等、failures空、Job PID空、child wait0、1000matching、20頁及ordered digest與原固定契約一致，全部成立。page0 read分別237113300ns／208542900ns，僅記錄原始cold樣本，不授予完整p95門檻。Owner持有cold_04 handle並依原授權順序執行，不以Root觀測重啟測試。

### Component tuple 完整矩陣效能未通過

六角色完成後，Root直接讀warm `C:/t/p01cur_rd_a29f465a51/child_result.json`，對三類各30個elapsed_ns原始樣本排序，使用nearest-rank第29筆獨立重算：page_flip=239469500ns（239.4695ms，通過）；filter_select_and_page=1074363400ns（1074.3634ms，失敗）；global_sort_select_and_page=344744500ns（344.7445ms，失敗）。不以角色readback passed或單元測試推導performance passed。較前一個lexical-only候選的filter525.9606ms及sort219.2445ms更差，仍需診斷，不宣稱原因已確定。

Owner報告六角色source/store起訖一致、Jobs清空；Root已直接核前五cold收據，warm完整postflight另待查。禁止重跑相同矩陣或補預暖。下一步只使用已產profile/fullsource檢查新共享預算、scope與eligibility：前次strict renderer581次，本次11102次，須查明純詞法memo是否失效／耗盡；未證實前不把退化全歸I/O，也不放寬fresh checks或300ms門檻。

Root續核warm supervisor/child：source/store起訖equality成立、failures空、JobPID空、childwait0、cleanup completed；child write/network/SQL/subprocess拒絕或嘗試皆0、unexpected source modules空、三類樣本恰30/30/30。六角色readback/隔離清理證據完整接受，效能門檻仍失敗，不再重跑同一候選。

### Profile 函式名稱與計數更正

Root直接讀warm filter的完整top_functions_by_cumulative_time：`to_internal_io_path`與memo方法`render`為11102次；strict函式`_render_internal_io_path`為5921次，不能把方法呼叫次數當strict miss數。`_validate_absolute_syntax`為6415次，Path.__new__97582次、parse_args100650次，components494次。前段「本次strict renderer11102」是owner摘要混淆，以上直接原始profile讀值取代它。strict renderer仍比前次581次顯著增加，但快取耗盡的具體原因須由純CPU診斷證明；不能以profile cumulative times直接加總或當p95。
