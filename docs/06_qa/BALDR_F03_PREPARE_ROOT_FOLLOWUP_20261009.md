# F03 三路準備：獨立審查後補正

狀態：實作／驗證中，不授共同 reader 資格。承接 `ed8b0506`，完整 F03 query、UI、收藏與跨程序閉環仍未完成。

## 審查結果與實作範圍

獨立 Luna Max 審查發現兩項應在共同 issuer 前補齊的問題：三個 collector 的可變 entries list 沒有保留原 callback entry 參照，跨 lane 相等不足以拒絕三路一起被替換並重算 self hash；group 雜湊前呼叫 MA index `to_dict()` 與 parent `asdict()` 會建立全量複本，不能以後續串流雜湊宣稱整段沒有全量複本。

先在三路 callback 當下保留有界、不可變的 entry 參照與 exact snapshot pin 紀錄，prepare 開始及結束都比對原參照；poison 清除全部紀錄。保存的是 compact entry 參照，不是 raw snapshot 或重新計算金融證據。只使用原 exact snapshot／cutoff，availability unknown、historical PIT false 保持。

後續移除 group 層的全量 MA payload 與 parent ledger 深拷貝。既有 MA index 建構仍有全量 canonical materialization；在真正修改並驗證前，此限制必須保留，不能宣稱完整 streaming／100,000 股記憶體驗收。F12 C3 的 MA source pin 正凍結，不在完整 Main 終態前改動 MA 模組。

## 回滾清單

| 檔案 | 類型 | 變更／回滾 | 風險 |
|---|---|---|---|
| `app_module/daily_market_technical_universe_projection_group_v2.py` | 修改 | 加 callback provenance；僅反向套用本切片 diff | 三路 group observer 受影響；不能覆寫其他改動 |
| `app_module/daily_market_technical_universe_projection_group_prepare_v2.py` | 修改 | 核對原 callback 參照及精確 pins；僅反向套用本切片 diff | 既有 group prepare 測試需重驗 |
| `tests/test_daily_market_technical_projection_group_prepare_v2.py` | 修改 | 原參照、同步替換及晚到替換負例；僅反向套用本切片 diff | 測試須保留首紅證據 |
| 本文件 | 新增 | 移除本文件前確認沒有新增入口依賴 | 不刪除原 QA 收據 |

回滾前核對最新 HEAD／dirty ownership，只撤此切片，重跑相關 group／prepare 測試。原始資料、正式排程、其他 agent 文件與本機 QA 封套不回退或刪除。

## 驗證狀態

待測，不把先前 7／3 項 preparation 通過當作新 tamper contract 已通過。共同 issuer 仍須沿唯一 F17 verified-bundle 發行邊界內部 prepare；不能接受 caller supplied candidate，也不能先發單獨 MA session。

兩個修改的 source module 型態檢查通過。第一次測試命令誤用不存在的 group 測試檔名，exit 4、沒有收集測試；保留 `output/qa/resume_root_validation_20261009_a/three_member_provenance_followup_attempt01.log`。第二次已修正檔名，實際結果待終態，記錄於同目錄 `three_member_provenance_followup_attempt02.log`。

第二次已終態：**13 passed／361.85s，exit 0**。實際正例涵蓋完整 257 included 母體、兩個 parent；query selection 只選最後一股，並未把 preparation 母體縮為一股。舊 MA serializer 與舊 parent `asdict()` canonical bytes 作 oracle，新串流 SHA／byte count 均相同。同步重算三路 transport、自我 hash 有效但 callback entries 被替換、晚到替換等負例均拒絕並 poison。targeted mypy 兩個 source modules 無錯誤；此結果不補授 reader 資格。

獨立審查另指出：provenance list 本身仍是私有可變狀態。這次拒絕模型涵蓋 collector rows 被替換、ledger 保持原 callback 記錄；沒有證明能阻止同一程序直接同時偽造 collector 與私有 ledger，不能稱為不可偽造 seal。唯一 issuer 後續不得接受 caller supplied preparation；正式資格必須由同次內部 verified-bundle 流程授予。新增 refs 僅證明筆數受 stock 上限約束，Python object overhead 尚未量測且不含於 canonical byte budget；完整 100,000 股記憶體驗收仍待辦。

## 並行工作實際狀態

P01 六角色矩陣 C 已執行一次，五個冷啟動與一個暖操作程序均 exit 0、來源與 store 前後一致、清理完成。暖操作每類 30 樣本，原 300 毫秒門檻保持：篩選 p95 618.493 毫秒未過；排序 246.491 毫秒、翻頁 208.060 毫秒。冷啟動至第一頁 p95 25.931 秒。這是隔離候選的量測，不是完整產品效能驗收。封套：`output/qa/p01_1000_component_tuple_memo_candidate_20261009_c/six_role_matrix_aggregate_v1.json`。

F12 C3 完整 Main 首次執行 exit 1，拒絕代碼 `parent_initial_personal_json_not_readonly`；原收據未保存當時的 mode/message，不能直接歸因產品來源錯誤。清理另遇 QA 呼叫不存在的 worker helper；後續 job helper 亦需核對真實 API。首紅封套保持，補正前不宣稱 Main 閉環通過。H20 O 仍只完成靜態檢查，尚未執行真 source-port／SQLite 正例；reader replay 與 storage config 錯 root/hash 負例仍未覆蓋。

root 從暖操作原 `child_result.json` 各 30 筆 elapsed_ns 獨立重算 nearest-rank p95，三類結果與 aggregate 相同，90 筆 status 均 `ok`；六角色 cleanup 沒有 active job PID。F12 另存事後獨立 `readonly_postflight_20261009.json`，13 roots SHA 與原 before 一致、58/58 pins 相符；原 receipt 的 after 仍為 null，沒有冒充補造原當次 after。原 merged stdout 無法從 compacted context 逐字取回，缺口明示保存。
