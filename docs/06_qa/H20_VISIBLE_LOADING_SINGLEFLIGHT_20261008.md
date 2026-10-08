# H20 可見等待、取消終態與單一讀取

H20頁已有真實核驗階段與等待秒數，但切入前的結果區捲動位置可能讓狀態不在viewport；重複觸發會另排完整讀取，取消也曾在原生執行緒終止前解鎖。來源版補件會將狀態帶入可見範圍，讓同一worker維持至native_thread_finished，取消後保持安全收尾狀態與操作鎖定，完成後列出總列／可研究／未知。

不改來源reader、SQLite安全副本、sealed view核驗、快取或模型／金融計算。晚到訊息仍核對generation、設定、read root及worker身分；未知列與來源過期結果不升格為可研究。

## 中央驗證

Root session37921 terminal0，三檔合併12 passed／31.85秒：`test_ui_qt_personal_h20_cohort_integration.py`、`test_ui_qt_personal_h20_mainwindow_saved_journey.py`、`test_personal_h20_sqlite_ui_integration.py`。所有來源由隔離合成fixture產生，真MainWindow／TaskWorker／public reader／typed sealed view，沒有原SQLite或模型訓練。

覆蓋首次讀取前已捲至底部而loading仍可見、真progress callback、讀取期間single-flight、取消pending到原生終態、取消後重試、精確選股下鑽／返回、其他結果頁返回、設定過期、缺capture完整重核、關閉中取消與未知列。未知案例為總列1／可研究0／未知1，研究與收藏停用；已核view的暖下鑽沒有另開來源operation。合成來源main bytes前後相同，network attempts為0。

原5個舊測試在WindowStub缺少既有安全read-root方法時失敗；原紀錄保留，測試已改成6個真Main整合案例，不再以tuple/object偽造成功或保留舊取消語意。Root另有先前6項中央定向15.09秒通過記錄；不將其混算為額外獨立使用者。

UI必要檢查：Workbench85 passed／3.37秒，validator25 passed／0 failed／4 protected skips，full-roots mypy902 source files clean；validator前像保存在本次QA目錄。既有pandas FutureWarning與Qt weak callback disconnect RuntimeWarning保留。Compile與scoped diff-check於提交前再核對。

## 凍結內容與範圍

| 檔案 | SHA256 |
|---|---|
| ui_qt/main.py | `e0549a78952a60432dac3859209956357cbdc1055e33d0cd14c45abfa3a27a74` |
| ui_qt/views/recommendation_view.py | `8efe7d5834b2efcecc7e7d757a275f0d7b02c8446b294b59e550a528ec19a296e` |
| tests/test_ui_qt_personal_h20_cohort_integration.py | `7c9ac42b0dde6fddb1a9b22666472a3d4a62269dd559e7c53c13068de4115aec` |
| tests/test_ui_qt_personal_h20_mainwindow_saved_journey.py | `59996d3f32438c8e64ddb2d3ff56e9f0b485198eaa63a3884f6b1c9600cc8147` |

產品前像、葉片測試與root檢查點保存在已排除的`output/qa/h20_loadinggap_20261008_a`與`output/qa/f17_main_host_root_20261008_a`。只接受此來源版UI狀態與合成旅程；原十股18.8秒為先前單次診斷，不是本補件加速證據。包含本補件的固定exe／Native、原十股新候選、真人、冷暖p95及完整P00–P14／M1–M3仍待。
