# 1,000 檔研究效能：目前失敗與下一驗收

> **時點／版本：**本文記錄 2026-10-09 的固定來源、合成母體效能 gate 與後續 profiling 準備。下文「目前程式」接點是當時核對的 checkout／pin（文末列出），不是對後續 HEAD 的即時判斷；原效能 gate 未通過，亦沒有完整 Main／EXE／真人 UI 接受證據。

Root 實讀 `C:/t/p01_mc6g40xn/benchmark_result.json` 的完整 operation summaries，原 status 是 failed。這是固定來源、合成母體的來源引擎測試，沒有完整 Main／EXE／真人 UI p95 接受。

| 每類 30 次樣本 | 原 p95 | 300 ms gate |
|---|---:|---|
| 換頁（完整 operation） | 813.5101 ms | 未通過 |
| 篩選、選取與頁面 | 1208.0899 ms | 未通過 |
| 全域排序、選取與頁面 | 879.3598 ms | 未通過 |
| 單股 selected materializer | 73.059 ms | 通過此類 |
| 跨 segment 16 股 materializer | 290.0902 ms | 通過此類 |

五個獨立 cold processes 的 launch-to-first-page 中位數為 93.1281177 秒，p95 為 93.3948601 秒。warm worker 的 initial strict read open 為 16.7770036 秒、base query／selection 125.5487 ms、first-page materialization 773.6064 ms。這些分項不是直接的根因證明；不能把單股或 JSON decode 小測通過，當作完整換頁／篩選／排序達標。

## 下一切片的順序

先完成真正 F02 全母體 query matrix 與來源資格／硬排除／unknown／排序／分頁 oracle，再使用同一保存的 1,000 檔母體定位效能。不得為了 benchmark 縮小母體、只排序當頁、略過 hash／source identity／cancel 或改分母。

profile 至少分辨：query 解析與驗證、global selection／sort、selected row materialization、segment／parent inventory 檢查、事實序列化、程序 bootstrap／strict open，以及 wall／CPU／讀取 I/O。目前只有上述總分項，尚不足以核定哪個函式應改。已驗證 session 內可評估有界、來源固定的 index／warm page reuse；資格失敗、來源變動或 session 結束必失效，不以全域常駐快取替代來源核驗。

修正後同版、同母體、同 operation 邊界重測每類至少 30 次、五個 fresh cold processes，保存逐次原始耗時、pins、resource 與程序終態。後續仍需完整 Main／EXE 相同版本與真人等待／取消體感；本文件不宣稱效能已改善，也不要求使用者現在重測舊 EXE。

## 中央補讀資源分項

Root 再讀同一原 benchmark 的 warm operation summary：30 次換頁累積 CPU 20.828125 秒／read 138,756,460 bytes／3,920 次；篩選累積 CPU 22.3125 秒／read 464,880,558 bytes／13,056 次；排序累積 CPU 24.171875 秒／read 158,515,620 bytes／4,510 次。三類 write bytes/count 都是0。這表示 profiling 需要同時量化 CPU 與讀取工作，不能只把慢歸因磁碟或把 UI scroll 修改算成引擎改善；read bytes 未具逐檔歸因，不能由這些總和認定哪個 artifact 被重讀。

後續 profile 保持三個完整 operation 邊界與原1000 included母體，保存函式耗時及 artifact 讀取計數；先確認 source pins／資格失效規則，再評估 session 內有界重用。此補讀沒有執行 producer、benchmark 或修改來源，原 failed gate 仍保留。

## 依目前程式確認的 profiling 接點

Root 已讀目前 `daily_market_technical_universe_v4_query.py`：`_ordered_candidates` 負責全域排序，`select_stock_codes` 建立完整selection，`read_selection_page`經`_materialize_page`按artifact分組後呼叫`_read_session_child_snapshots`，再逐筆`_make_row`與snapshot/source/sort值核對。`_read_session_child_snapshots`在有 reader-issued semantic proof 時走repository `read_selected_exact`，否則走`read_exact`。因此下一profile至少分這兩條真分支，記錄每operation的artifact數、選取列數、manifest/source核驗與row投影時間，不能僅以selected列數推定I/O成本。

此接點盤點只讀目前工作樹，尚未證明原frozen acd18a1e benchmark執行哪個分支；實際profile須先核frozen來源API/identity並記錄分支。不要為了計時跳過proof驗證、fallback完整核驗或取消檢查，也不把目前程式路徑當原benchmark慢因的證明。

## Profile 候選的版本對照要求

新profiler agent先找到q2897c／2897f269來源與readback f1a69b9d版本；Root已指出它與原failed `C:/t/p01_mc6g40xn` 的acd18a1e來源不同。下一候選須優先查原`source_benchmark_controller_acd18a1e.py`、source evidence/helper/qualifier與recovery pins，不能默默替換版本後將profile稱為原93秒／813ms慢因。若原資格或檔案狀態不允許重用，須明列理由、舊新程式差異與同1000母體pins，將新版profile與舊baseline分列。此處僅記設計審查，尚未profile或核效能改善。

## 三類 profiler WIP 審查

Root初讀新runtime候選已改回acd18來源與原store/report/controller/helper pins；三類操作已開始加入。然而supervisor仍有舊20261008 page-flip目錄／檔名／profile pin，runtime結果仍有舊單翻頁scope與profiler變數。已要求凍結前完整清理所有路徑、labels、變數及payload契約，做四檔名稱／模式入口檢查再交審；尚不執行native。cProfile與新增診斷guard都有量測成本，只供診斷，不當300ms／p95通過或原baseline慢因的直接證明。

Root續讀三個operation closure確認：page_flip沿已完整selection讀page10／50；filter沿兩個public rule match／AND建立query、完整selection、page0；global sort沿volume ratio desc建立完整1000selection再page0。未見先縮成當頁後排序的替代路徑。Filter合格筆數可低於1000，應核母體1000與完整matching selection，不錯誤要求1000筆均match；零matching的page語義仍由固定API決定。這只是候選操作邊界審查，不授native/profile或效能完成。


## 現版完整對照的來源邊界

Root實核HEAD d12f3e32672d90addc4c0e7ac0a478f2171bcfeb。新runtime archive須分別記現版runtime pin與原2897 producer／acd18 readback pin；不能改原封套以假稱新runtime就是原producer。原1000 sealedstore／recovery保持，先證明method/schema兼容後執行完整30sample三操作；若合法重用不成立需提出具體契約證據，不能退成小helper量測。此準備尚非性能gate通過。
