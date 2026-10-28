# FlowSignalEngine 單趟事件掃描 QA — 2026-10-27

## 變更範圍

`FlowSignalEngine._process_single_stock()` 原本分別掃描 `agg.events` 建每日淨量、計算方向性分點集中度、再建一次每日淨量給 sparkline。現在一次遍歷累積每日淨量與總淨量方向的分點淨量；連續日計算與 sparkline 共用同一份每日淨量。未修改來源範圍、事件品質過濾、數量單位、分數公式、Decimal 信心折減、集中度門檻、文字理由／標籤或排序。

## 驗證

- Broker Flow engine 與 dashboard query service 回歸：**44 passed**。收據 SHA-256 `4c941b0807979072a04deb19d164a075e5435bded0cc9227c5c60b524adccaae`。
- `mypy decision_module/flow_signal_engine.py`：無問題，1 source file。收據 SHA-256 `b1d25bea624b8e8eb213026f4fb32fce2113f5f1ebbc35d27dad5714972472e3`。
- 修改的 engine 與 unit test `py_compile` 通過。收據 SHA-256 `1e649a29846836d4352fa65d4df7996521a8ff51b0082feb45f67571910a5573`。
- 合成 A/B 以 HEAD `e6dc05a64cab07f17cd9010c4b53b33318311f95` 的 engine 作基線，使用 139,348 筆事件、1,631 檔、20 日、3 組暖身及 50 組交錯配對樣本。停用計時期間的自動 GC；同時記錄牆鐘與 process CPU 時間。完整 DTO 與物化 `BrokerFlowReadSnapshot` 的 dashboard snapshot 均精確相等。

| 測量 | HEAD p50 | 單趟版 p50 | p50 變化 | p95 HEAD → 單趟版 |
|---|---:|---:|---:|---:|
| Engine `generate_signals` | 75.397 ms | 65.376 ms | −13.3% | 87.291 → 75.024 ms |
| Materialized dashboard service（聚合＋engine＋摘要） | 149.502 ms | 140.684 ms | −5.9% | 171.627 → 165.934 ms |

完整 raw samples、輸出 hash 與方法記錄於 `output/tasks/flow-signal-single-pass-20261027/evidence/benchmark_flow_signal_single_pass.json`；受控執行收據 SHA-256 `16d9f247d0a1f6a2e9bd95666d6774813d576ee72f24107cb7879d0e2586ee7a`。

所有 Python 驗證由 task evidence 內的 root-owned Windows Job wrapper 執行；8 GiB memory／12 process／kill-on-close 限制讀回成功，結束無殘留程序。

## 界線

A/B 使用合成記憶體內事件與已物化來源快照；未讀 SQLite、正式資料或真實 Main window。量測支持服務層計算路徑改善，不能外推為正式資料庫或整體 UI 延遲；既有資料來源資格、日期範圍、Gate／PIT／ML 狀態均未改變。
