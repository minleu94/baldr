# 畫面銷毀警告與窄版控制項驗證

真257 Main旅程通過時，曾出現兩筆 `layout_helpers.py:380` 的 `destroyed()` disconnect RuntimeWarning。原因是view的destroyed回呼在dispose中再次斷開正在發送的同一回呼。修正只從待斷線清單移除這一個精確callback，其餘訊號斷線、model及dispatcher pending清理維持。

新增測試捕捉Python RuntimeWarning，核disposed、dispatcher無pending及刪最後參照後weakref可回收；不以全域warnings忽略或只抓Qt訊息替代。中央獨立合跑layout helper與推薦layout：19 passed／12.62秒，原log `output/qa/root_ui_gate_20261008_d/helper_recommendation_root.log`。分支原log及前像在 `output/qa/layout_helpers_destroyed_signal_20261008_a/`。

窄版新增390×844、含184px導覽的206px內容區及760／900px外殼。驗每個個人控制列無重疊、短控件可完整捲入、過長文字或過寬控件能到首尾；允許既有水平捲動，不把一次ensureWidgetVisible只露長元件上緣誤稱產品裁切。不新增手機版產品承諾。

強制檢查：Workbench85 passed／3.36秒；validator25 passed／0 failed／4 skipped；full-roots mypy913檔clean，log在 `output/qa/root_helper_gate_20261008_e/`。這是source功能接受，不代表候選EXE或真人接受；正在建置的固定acd18a1e候選不含本輪helper清理。

## 回滾清單

| 檔案 | 變更 | 回滾方式 | 風險 |
|---|---|---|---|
| `ui_qt/widgets/layout_helpers.py` | 銷毀時略過目前destroyed回呼 | 只移除此段精確清單過濾 | 不回復整檔覆蓋其他修改 |
| `tests/test_ui_qt_layout_helpers.py` | 銷毀警告／清理／GC案例 | 本任務前像或移除新案例 | 保留既有Qt測試 |
| `tests/test_ui_qt_recommendation_layout.py` | 個人區窄版可達性案例 | 只移除本輪新案例 | 保留先前鍵盤閱讀測試 |

未修改原始資料、正式排程或金融計算；原失敗測試及其較嚴斷言皆保留在QA封套。
