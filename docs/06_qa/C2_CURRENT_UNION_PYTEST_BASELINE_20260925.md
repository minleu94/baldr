# C2 current union pytest 基線（2026-09-25）

## 裁定範圍

Root 接受本次凍結的 136-test／78-source union 作為歷史 C2 pytest 基線，並釋放該時點相同 bytes 的 source freeze。其後 current union 擴為 141 unique tests／88 sources，於 2026-09-25 得到 1,860 passed／5 skipped／34 warnings、exit 0；Workbench 84P、broad mypy 724/0、67-file py_compile 通過。C2 裁定為 `ACCEPTED_WITH_NAMED_QA_BASELINE`，唯一具名例外是 Update validator 的 WinError 32 TEMP SQLite teardown（exit 1，不稱全綠）。current 收據與限制見 [C2 mandatory gates report](C2_MANDATORY_UI_STATIC_GATES_20260925.md)。本文件保留 136-test 歷史基線身份，不將 2026-09-25 final receipt 混作當時 bytes。

## 凍結輸入與 NP2 路由

| 項目 | 收據 |
|---|---|
| Manifest | `C:\Users\archi\AppData\Local\Temp\c2_luna_union_20260925_be52bcaa\manifest.json` |
| Manifest SHA-256 | `64D7EB0FD2A7E7ED9E775562650B58E6D8B51EE5E99722785CD9EB113CDF0291` |
| 綁定 HEAD | `bec423eef1d9e9d4a32410dac96cd233304489aa` |
| 輸入檔案 | 136 個去重後可執行測試 + 78 個來源檔，共 214 個凍結輸入；依 R015 退休紀錄排除已刪除的 `tests/test_recommendation_save_coordinator.py` |
| 執行腳本 | `C:\Users\archi\AppData\Local\Temp\c2_luna_union_20260925_be52bcaa\run_union_np2_fixed.ps1 -qaProfile NP2` |
| 執行環境 | Python 3.11.9 / NumPy 2.3.5 / Pandas 2.3.3 |
| 隔離根目錄 | `C:\Users\archi\AppData\Local\Temp\c2n2_fix_luna`（`TEMP`／`TMP` 指向此處；pytest basetemp 位於 `root\p`；`PROFILE=test`） |
| 結果 | 1793 passed、5 skipped、34 warnings；結束碼 0 |
| pytest log | `C:\Users\archi\AppData\Local\Temp\c2n2_fix_luna\pytest.log` — SHA-256 `BD4A7AC06C28C7B5950D09A9BF4458C774B650F531A5DD68C38B1AB6E1BA3A96` |
| 執行收據 | `C:\Users\archi\AppData\Local\Temp\c2n2_fix_luna\receipt.json` |

執行前後驗證與獨立回讀均確認 manifest SHA 相符、HEAD 未變、214 個輸入檔案 hash 全部符合 manifest，漂移數為 0。收據所列 log hash 也與 log bytes 相符。

五個 skip 均保留原狀，不計為通過：`tests/test_c1_legacy_query_readiness.py:439` 一例及 `tests/test_r012_recommendation_artifact_persistence.py:1160,1191,1211` 三例因 Windows 主機回報 WinError 1314 而略過；`tests/test_r020_numeric_runtime_differential.py:685` 因本 runtime 的 `longdouble` mantissa 並未寬於 `float64` 而略過。

## 既有 UI gate 收據與目前 bytes

前次 C2 preflight 的 UI 檔 hash 仍保留在 [`C2_NON_ML_CONSUMER_UNION_PREFLIGHT_20260925.md`](C2_NON_ML_CONSUMER_UNION_PREFLIGHT_20260925.md) 作為歷史 continuity 證據。current C2 gates 已另以 fresh TEMP 完成：Workbench `84 passed`；broad mypy `724 source files／0 issues`；Update validator 兩次皆為 `25 passed／1 cleanup failure／4 skipped`、exit 1，依既有 R023 同類 teardown exception 具名接受。完整 logs、source fingerprints、skip reasons 與限制作為 [C2 mandatory gates receipt](C2_MANDATORY_UI_STATIC_GATES_20260925.md) 保存。

| 檔案 | SHA-256 |
|---|---|
| `ui_qt/views/portfolio_view.py` | `0FFD4E1EA8C241D5A552AFE6612FAE9C84D68E369C26A68B05B7584817D2EB2A` |
| `ui_qt/widgets/user_declared_holding_research_widget.py` | `4CF2332011CDC7A2366054B645530C88516DFBF9AA692B56C9642F96092B2806` |
| `tests/test_ui_qt_portfolio_view.py` | `95E6104FED145C3781A7FF6ED79721FA4957AF88489487BEAFBF41BF5DA22630` |
| `tests/test_ui_qt_user_declared_holding_research.py` | `6DC4AFE1E8450C5601977EFBE65B1AB8D877B37EF5BF6F1861E4514EA9A2EAC4` |

## NP1 執行環境分類

NP1 路由使用相同凍結 manifest，結果為 1775 passed、18 failed、5 skipped。其中 17 個失敗來自 R026 capability/model-facts 檢查；該切片明確只支援 NumPy 2.3.5，並拒絕 NumPy 1.26.4，因此維持為不支援 runtime profile 的失敗，不改列為通過。剩餘的 readiness owner-packet 失敗則由執行腳本的 TEMP 配置造成：pytest basetemp 與 OS `TEMP` 是同層目錄，而 fixture 要求 packet 位於 `tempfile.gettempdir()` 之下。以 `TEMP=runRoot`、basetemp `runRoot\p` 在新的隔離 NP1 根目錄重跑該單一案例後通過：1 passed、結束碼 0；log SHA-256 `D7B724EBD4E87B87755578C33078FBEBF63BB1F3C8E99DDC03B4A076760E97D5`。未重跑完整 NP1 路由。

較早的 NP2 嘗試使用相同的 TEMP/basetemp 分離配置；確認環境問題後，於測試進度 40% 中止。其部分 log 位於 `C:\Users\archi\AppData\Local\Temp\c2n2_luna\pytest.log`，SHA-256 為 `A29F12A1AF80144AEC4AAF700C9EF206F53507737D0B219B0E4F640C9D674930`。該 log 不是完整路由收據，已由上方修正環境後的 NP2 路由取代。

C2 union 執行後，R020 獨立 recovery slice 擴充了 `tests/test_r020_process_crash_recovery.py`；因此本 C2 manifest 是路由執行時的凍結快照，不代表擴充後的當前測試 bytes。後續測試 hash 與 targeted route 收據見 [`R020_PROCESS_CRASH_RECOVERY_HARD_EXIT_QA_20260925.md`](R020_PROCESS_CRASH_RECOVERY_HARD_EXIT_QA_20260925.md)。

## 安全與變更

所有 pytest 使用合成資料、獨立 TEMP/DATA_ROOT/OUTPUT_ROOT、`PROFILE=test`；未執行 scheduler、正式資料、模型 rebuild/promotion，也未開啟或操作互動式 UI（union 中的 Qt 測試以 offscreen 模式執行）。C2 union 路由執行期間 HEAD 與凍結輸入未改變；未 stage、commit 或 push。
