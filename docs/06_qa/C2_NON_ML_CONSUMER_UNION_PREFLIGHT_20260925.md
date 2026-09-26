# C2 非 ML Consumer Union 預檢（2026-09-25）

## 結論與範圍

本次是 C2 non-ML consumer union 的 bounded preflight，不是 C2 release，也不代表 R020、TMP-REC-04 或 TMP-NUM-01 已完成。NP1 與 NP2 在同一份更正後的 80-test／54-source manifest 上皆完成，manifest 的 134 個項目在每次執行前後都與實際 SHA-256 相符，HEAD 固定為 `bec423eef1d9e9d4a32410dac96cd233304489aa`。

這個 union 仍未涵蓋 R026 source-backed historical replay 的完整消費路徑、C1 ML 的完整 union，以及 R029／R031 的 residual。不得以本收據解除 C2 或其他 Wave gate。

本次 UI 修正只處理 widget 生命週期，不改使用者可見流程、資料內容或結果判讀，因此不需更新 Manual。

## 修正摘要

- [portfolio_view.py](../../ui_qt/views/portfolio_view.py)：延後還原 splitter 尺寸時，將 `QTimer.singleShot` 綁定至 `PortfolioView` receiver；view 銷毀後 Qt 會取消該 callback。
- [user_declared_holding_research_widget.py](../../ui_qt/widgets/user_declared_holding_research_widget.py)：worker 的 `finished`、`error`、`cancelled` 改連至 widget receiver slots，不再由 lambda 捕捉 widget、model 或 button。既有 generation、selection 與 worker release 流程仍由原 handlers 處理。
- [test_ui_qt_portfolio_view.py](../../tests/test_ui_qt_portfolio_view.py)：`test_portfolio_drill_down_passes_selected_stock_to_parent` 現先呼叫既有 `app()` helper。原單測在 `QApplication` 建立前先建 `QWidget`，Windows 子程序會以 `-1073740791` 結束；加入 setup 後單例、pair 與三檔路由皆通過。
- [test_ui_qt_user_declared_holding_research.py](../../tests/test_ui_qt_user_declared_holding_research.py)：以 barrier 測試 worker 尚未完成時刪除 parent，確認晚到 signal 不觸及已刪除的 table model 或按鈕。

## Freeze manifest

Corrected manifest 位於 `C:\Users\archi\AppData\Local\Temp\c2u_testfix_e2a7ea84d1a0425a97c6cccc5aed3cb5\manifest.json`，SHA-256：`DC0CCC69C8D02B8E4AA32967EC00E1ABD18133E507936EAE2E53931493CAB0C4`。內容是 80 個去重後的測試路徑與 54 個去重後的 source 路徑，共 134 項。

相對於前一份 80/53 manifest，source 清單保留原 53 項並新增 `ui_qt/widgets/user_declared_holding_research_widget.py`；本次改動的 `test_ui_qt_portfolio_view.py` SHA 亦已更新。NP1、NP2 route 執行前、執行後均核對同一份 manifest 及所有 134 個檔案，未見 drift。

### 已更正的舊 manifest

先前臨時 manifest 曾有 `test_count=80`、`source_count=53`，但 `sources` array 實際有 54 項。使用該錯誤 metadata 的 union receipts 不作本次證據。以下 NP1／NP2 receipts 均使用上列 corrected manifest；歷史錯誤 manifest 與其執行紀錄保留在 TEMP，沒有覆寫成新證據。

## 最終驗證收據

所有 pytest route 使用 `PROFILE=test`、新建 TEMP、`DATA_ROOT`／`OUTPUT_ROOT`，UI 設 `QT_QPA_PLATFORM=offscreen`；pytest 的 `--basetemp` 位於該次 TEMP。Union route 由 manifest 的 `.tests[].path` 展開，使用 `-q -o addopts=`。

| Route | Profile | 結果 | Log 與 SHA-256 |
|---|---|---:|---|
| Corrected 80-test union | Windows / Python 3.11.9 / NumPy 1.26.4 / Pandas 2.3.3 | 1107 passed, 5 skipped, 34 warnings；pytest 56.11s；exit 0 | `C:\r20q\c2ul_n1_final_f3a3a147\pytest.log` — `CF73EE9566D50AFE5F4C9D5BFACE5DE3496852705F7BE06AE3B265951BF387CD` |
| Corrected 80-test union | Windows / Python 3.11.9 / NumPy 2.3.5 / Pandas 2.3.3 | 1107 passed, 5 skipped, 34 warnings；pytest 55.79s；exit 0 | `C:\r20q\c2ul_n2_final_a60073a4\pytest.log` — `5FECEB839698B8F1F0EA3C325FD857E7AD5B9EAE2ABFB62F45A7A1F1C3BC408E` |
| QApplication bootstrap／drill-down／context status 三個 UI tests | Win32 / `.venv` | 3 passed；exit 0 | `C:\Users\archi\AppData\Local\Temp\ui_pair_qapp_b121b5a9738c4d7dbd6b4d0268f78dee\pytest.log` — `9345BDE524D0264B1B8F7A9E50D8E6DE34432552ED1E3D307936C1722AF2D311` |
| Portfolio、context status、user-declared widget 三檔 | Win32 / `.venv` | 39 passed；exit 0 | `C:\Users\archi\AppData\Local\Temp\ui_three_qapp_8b31c18fd84d4baf8c8379e038e474d7\pytest.log` — `76EE69EA64EAEF1D1335D84D117BB20E92B7317C2370C3D68E63DC9AB33CA5C8` |
| QApplication setup 修正後 drill-down 單例 | Win32 / `.venv` | 1 passed；exit 0 | `C:\Users\archi\AppData\Local\Temp\ui_drill_qapp_55cfdaeff7984f32b5d2a1f96c9a0773\pytest.log` — `C24F590F555F7C55A6993B89D8FFA381D0956F45820533E70EA63466311F8A02` |
| 修正後 drill-down 單例之 QThread exit 對照 | Win32 / `.venv` | 1 passed；exit 0；wait 前／後均有 0 個 live workers | `C:\r20q\worker_exit_compare_cbc10a3c\diag.log` — `183E9D263D0D8C13689FEA51E2B6DEB4ADE9BCA18B8BEC6C8CB2F8D2BBA7AC7D` |

強制 UI gate 於兩個 production lifetime 修正後重跑：

- Workbench：84 passed，exit 0；`C:\r20q\ui_workbench_final_dabb2685\pytest.log`，SHA-256 `71505355A2A51C2A8F2DC7919D0CACBF45EE4A9575BDE15D5F10222D3F7F76B0`。
- Update QA：25 passed、0 failed、4 skipped，exit 0；`C:\r20q\ui_update_final_d8bfa4b1\qa.log`，SHA-256 `EA04970853EE16CDEAB264B384AB328E2B004AA320584A2F87ABE295172F68AF`。測試資料與 artifacts 使用本次 TEMP；腳本另將詳細 report 寫到 repo 的 `output/qa/update_tab/VALIDATION_REPORT.md`。
- Broad mypy：`Success: no issues found in 717 source files`，exit 0；`C:\r20q\mypy_final_3e297d43\mypy.log`，SHA-256 `64C4EBAE5BD7F0AE59FDBDD814D883B0859D6B42F5C71486DCF508EAD55BBC1E`。
- 四個變更 Python 檔 `py_compile` exit 0；`git diff --check` exit 0。

## 生命週期診斷與獨立檢查

- Splitter callback 的修前直接測試曾在 view 銷毀後仍執行；red log `C:\t\qtlife_destroy_red_633e\pytest.log`，SHA-256 `E9EAC68FEB5E8FAE1E5533178B024369B715675E9D418EDC89400D9FA342ECB7`。receiver-bound 測試涵蓋 view 存活時 callback 執行，以及銷毀後 callback 取消。
- Worker 晚到 callback 修前 red log：`C:\t\worker_red_e463\pytest.log`，SHA-256 `8F6C9BB0CACA78E5581C789F7304BA7D5012AE8655C3B6C1D8C723301C02680F`；barrier 測試修後 green log：`C:\t\worker_green_b0d5\pytest.log`，SHA-256 `FBC152957B35A7A3A4725C17E32918F23F5BD96CCE7574AA2D01BA5068369BE2`。獨立 error-path probe 亦確認錯誤摘要保留、`_refresh_worker is None` 且 `running_task_workers()` 清空：`C:\t\qt_lifetime_20e533c8\worker_error_probe.log`，SHA-256 `E291E37B3378614A4B306B4A00B9655433170E871938A3F7DEE8C83AB1902D8C`。
- 獨立 reviewer UI 三檔 fresh TEMP route：50 passed，exit 0；`C:\t\qt_lifetime_f7aab617\pytest.log`，SHA-256 `7368C9BDE62D71BE6ECF0DE5D2939770F473969AA289FBC152DC4C8AE7823330`。該 route 未包含後來加入的 `app()` setup 單行；R015 隨後對此 test SHA、corrected manifest、NP1／NP2、Workbench、Update QA、mypy 與單例／pair／三檔結果完成定點 readback，並另核 error-path probe，未見 P1/P2。
- 有一次在未先建立 `QApplication` 的 isolated test process 以 `-1073740791` 結束；`C:\r20q\ui_prefix_verbose_n1_6c5ef316\pytest.log`，SHA-256 `AF41CBBAC84B9617D084ED487C90CD0DA39B450784FF77C40CB45789F574F9E5`。在 test 開頭呼叫 `app()` 後單例、pair、三檔均通過，故此現象歸為測試 setup 次序錯誤，不計作產品或 worker callback 回歸。
- QThread exit 對照在 drill-down 單例結束時已觀察到 0 個 live workers；因此它沒有證明「尚有 worker 執行時的 interpreter exit」行為。worker parent-destruction barrier 與 error-path probe 是分開的證據，不能合併成所有背景 worker shutdown 情境已證明。

## 變更檔 SHA-256

HEAD：`bec423eef1d9e9d4a32410dac96cd233304489aa`

| 檔案 | SHA-256 |
|---|---|
| `ui_qt/views/portfolio_view.py` | `0FFD4E1EA8C241D5A552AFE6612FAE9C84D68E369C26A68B05B7584817D2EB2A` |
| `ui_qt/widgets/user_declared_holding_research_widget.py` | `4CF2332011CDC7A2366054B645530C88516DFBF9AA692B56C9642F96092B2806` |
| `tests/test_ui_qt_portfolio_view.py` | `95E6104FED145C3781A7FF6ED79721FA4957AF88489487BEAFBF41BF5DA22630` |
| `tests/test_ui_qt_user_declared_holding_research.py` | `6DC4AFE1E8450C5601977EFBE65B1AB8D877B37EF5BF6F1861E4514EA9A2EAC4` |

## 補充：source-backed historical replay ML 小路由

另以 `PROFILE=test`、短 TEMP，並將 `DATA_ROOT`／`OUTPUT_ROOT` 與 pytest 暫存目錄隔離，完成一條 source-backed historical replay ML 補充路由。此路由包含：

- `tests/test_recommendation_historical_replay.py`
- `tests/test_r026_calibration_legacy_preparation_baseline.py`
- `tests/test_r026_historical_raw_snapshot_custody.py`
- `tests/test_ml_historical_snapshot_provider.py`
- `tests/test_ml_historical_feature_computation.py`
- `tests/test_ml_historical_feature_builder.py`
- `tests/test_ml_historical_label_builder.py`
- `tests/test_recommendation_service_calibration_integration.py`

結果為 **90 passed／13.50 秒**。Log：`C:\t\c2ml_temp\pytest.log`，SHA-256 `938D13A7EF3D0FDB66DE29FBC00A6D3BADEB1FB7358501B0F33E2EAE4FFDA64D`。執行時 source identity：`app_module/recommendation_service.py` SHA-256 `947BE55EA2F9A5B7B9325B6D544CD81AD97E9FDA39A9C6DC1F07932090DC8EF6`、`app_module/recommendation_calibration_consumer.py` SHA-256 `49B9889376DBFBC004DDDE0D15F18BCEDE9F4C6FFB83D261452594189499ED48`；`tests/test_recommendation_service_calibration_integration.py` SHA-256 `075B980B7BDC75AF9E25DAC239C1BB12167EAA10F61B25B1CDF896DF02EFA3F6`。

這是 source-backed ML 小路由補充收據，不是 C2 gate，也不等於 C1 ML 完整 union、完整 R020／V-REPLAY、R026 或 R029／R031 驗收。C2、R020、`TMP-REC-04`、`TMP-NUM-01` 與 `TMP-ML-01` 仍 open。

## 當前 manifest 漂移與 C2 尚缺（2026-09-25 21:19:55 UTC 唯讀重核）

本次以 `C:\Users\archi\AppData\Local\Temp\c2u_testfix_e2a7ea84d1a0425a97c6cccc5aed3cb5\manifest.json`（SHA-256 `DC0CCC69C8D02B8E4AA32967EC00E1ABD18133E507936EAE2E53931493CAB0C4`，manifest 記錄 HEAD `bec423eef1d9e9d4a32410dac96cd233304489aa`）逐項重核目前工作樹；當前 Git HEAD 仍為 `bec423eef1d9e9d4a32410dac96cd233304489aa`。134 個項目皆存在，其中 6 個 SHA 不符：1 個 integration test 與 5 個 source，詳見下表。前述 NP1／NP2 各 1107 passed、5 skipped 的結果仍是其執行時 manifest 的歷史 bounded 收據，不代表目前工作樹已通過該 union，也不能作為 C2 full gate 的 PASS。

| 類別 | 路徑 | Manifest SHA-256 | 目前 SHA-256 |
|---|---|---|---|
| Test | `tests/test_recommendation_service_calibration_integration.py` | `FE4DC7EF45D47A52E9A9F37BCB5671C387222D230DEBE2289FFCEF747AE95FF7` | `075B980B7BDC75AF9E25DAC239C1BB12167EAA10F61B25B1CDF896DF02EFA3F6` |
| Source | `app_module/recommendation/historical_snapshot_custody.py` | `A1F9DEB3015AE878090BA9DC7C3252C1CC674D9BE1160E52265668356310E5C0` | `FC00C47719847CEBC25B0DCA7AF25F2EC51A4AB49C182FFA5954FC244373EA51` |
| Source | `app_module/recommendation/model_resolution_facts.py` | `662A646CFBD0DF60EB361448DE4BBCDC2213F21BC76AF8051070AB8A6395E41A` | `5898378B4EB6FE0038DDC750607B6DB183F7E48767A3255684A5973CE2040C59` |
| Source | `app_module/recommendation_calibration_consumer.py` | `EF0878163FC315D8B9C532BB429247E8034766CECC964810BB5FE9CB2BD790AC` | `49B9889376DBFBC004DDDE0D15F18BCEDE9F4C6FFB83D261452594189499ED48` |
| Source | `app_module/recommendation_service.py` | `3A7DB2C56B0A435E21D99F75AEF14B904FA18BF42B40429E279AE5B499E35AB8` | `947BE55EA2F9A5B7B9325B6D544CD81AD97E9FDA39A9C6DC1F07932090DC8EF6` |
| Source | `data_module/ml_historical_snapshot_provider.py` | `CCF2FA00EB3A41E319FC67CFF3B64F12A5222D607A3E6FC0E982F28B262017E4` | `1BE1E2F37AE49B9753D52ED5344AD7C1363F165E7E926B8E8616DBA4D00208D7` |

目前 R020 的獨立 manifest（40 個 tests、6 個 sources，共 46 項；SHA-256 `3D27664FDB98E2607C57E6F85A2CD0DF4F17B8BFD5BC9D9E5768CC15390A63F2`）為零 drift；這只說明該份 manifest 與目前檔案一致，不代表 full V-REPLAY 已完成。上節 90P source-backed 路由是另一份有界補充證據，也不是 C2 full gate。

C1 狀態以 [`C1_CHECKPOINT.md`](../../docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/C1_CHECKPOINT.md) 為準：最終 engineering gate 為 PASS。`C1_FULL_GATE_VALIDATION_REPORT.md` 的 `NOT PASSED` 是 reviewer／SOL 最終裁定前的 QA 執行快照，不是目前 C1 裁定。這不代表 C2 union 已通過；目前 80/54 manifest 漂移尚未重跑。

下一份可審的去重驗證 manifest 應在來源凍結後組成：既有 C1 42 個測試、C2 80 個測試、90P 補充路由新增的 7 個測試，再加 `tests/test_r019_scheduled_cutoff_provenance.py`、`tests/test_ui_qt_run_registry_compare.py` 與目前 R026 focused tests。按路徑去重，先重算並記錄所有 source/test SHA，再用 `-rs` 執行以保留 skip 原因；未完成該 route 前不把它稱為 C2 full PASS。R020、C2、`TMP-REC-04`、`TMP-NUM-01` 與 `TMP-ML-01` 仍 open。

## Gate 狀態

這份收據僅支持上述 bounded non-ML consumer preflight 與 UI lifetime 修補。R015 獨立 reviewer 對 UI route 與 corrected 80/54 manifest 定點複核未見 P1/P2；root 將本範圍判定為 bounded `ACCEPTED_SCOPE`。R020、C2、TMP-REC-04、TMP-NUM-01 仍 open；完整 R026 source-backed historical replay、C1 ML full union 與 R029／R031 residual 未由上述 bounded routes 覆蓋。沒有 stage、commit 或 push。
