# Journal 跨頁 worker gate 隔離診斷（2026-10-06）

指定案例 `tests/test_continuity_review_workbench_r1_integration.py::test_producer_backed_workbench_to_shared_report_journey_and_readback` 第373行，原等待門檻8000ms。僅一次 current（6d9a4316）與一次整合前 baseline（e61786bc、Temp leaf-module overlay）合成 offscreen 觀測；沒有放寬 predicate、修改 timeout 或重跑至通過。未讀正式資料或操作 Native。

| 觀測 | current | baseline |
|---|---|---|
| 原8秒predicate | false | false |
| Journey存在／載入 | true／true | true／true |
| report worker | running | running |
| read_report耗時 | 8.109秒 | 8.141秒 |
| gate失敗後terminal觀測 | 0.015秒 | 0.015秒 |
| error signal／exception | 無 | 無 |

兩者 deadline Python stack 均在 `read_report → list_saved_sources → fetch → Recommendation queries.get → legacy readmodel → legacy unchanged驗證 → scoped path → Windows no-follow → CreateFileW handle open`。Journey worker已清空；報告完成後 `_on_report_loaded`、reportLoaded、worker cleanup均在MainThread，最終「報告部分載入」。沒有卡死、錯執行緒回呼或 Journal selector 回歸的觀測證據；不能把32ms差異當效能結論。

原完整案例仍失敗，未走到後續 busy-close 子程序；外層延長只取 terminal，不算驗收通過。8秒門檻是否應保留需父層核定；若保留，legacy saved-source 重複安全讀取成本須獨立處理，不能直接放寬 no-follow 守衛或冒稱自然成熟待辦。本輪沒有 production修正，故未重跑251項。

原始收據留 `output/qa/journal_journey_worker_gate_20261006/`：current／baseline at_8s（完整堆疊）、events（粗階段與signal執行緒）、terminal、pytest logs、baseline overlay manifest與comparison；依git exclusions不提交raw。兩次使用隔離LocalTemp fixtures與允許Win32 handles的測試環境，不修改正式DB／registry。
