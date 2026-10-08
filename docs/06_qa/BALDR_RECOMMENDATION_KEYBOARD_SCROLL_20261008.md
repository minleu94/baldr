# 推薦理由鍵盤閱讀修正

使用者要求展開推薦理由後能完整閱讀分數拆解、排名門檻與排名因素。既有測試直接設捲軸值，沒有證明鍵盤能使用；新增真 QTest 在460×700視窗重現：文字區取得焦點，24次PageDown及Ctrl+End都沒有移動外層捲軸，末行仍在viewport外。

`_RecommendationReasonText.keyPressEvent` 現在僅於展開、內層捲軸沒有範圍時，把無修飾PageDown／PageUp及Home／End／Ctrl+Home／Ctrl+End交給最近的外層QScrollArea。收合、內層可捲動、找不到外層或其他鍵保持QTextEdit處理；文字選取及Ctrl+C仍保留。沒有推薦重算、策略／金融計算或來源變更。

中央獨立完整推薦layout測試6 passed／6.70秒，原log `output/qa/root_ui_gate_20261008_d/recommendation_layout_root.log`。新增測試核末行矩形真正進入viewport，而不是只設捲軸；亦核PageUp／Home與收合內層、複製正常。產品SHA `5f0faa96f246c62c7693e1771d538d88b72ae95a6544208d74b14650ed16edd5`，test SHA `cd9dbff9401cb63a6c43c394d4a0fdf9cd8b503840ff85a893d50c3c8be5a67d`。

本輪Workbench85 passed／3.42秒，validator重試25 passed／0 failed／4 skipped；首次sandbox合成fixtureWinError5報告保留。full-roots mypy第一次有MA草稿型別錯，原owner修正後完整重驗912檔成功，中央已讀原log `output/qa/f02_ma_query_v1_initial_filtered_publish_20261008_a/mypy_full_roots.log`。未建置含此修正的新EXE，真人尚待；不能要求使用者用舊候選驗新鍵盤行為。

## 回滾清單

| 檔案 | 變更 | 回滾 | 風險 |
|---|---|---|---|
| `ui_qt/views/recommendation_view.py` | 新鍵盤路由 | 僅回復本次keyPressEvent與imports | 保留其餘理由高度修正 |
| `tests/test_ui_qt_recommendation_layout.py` | 兩個原生鍵盤案例 | 回復本輪測試前像 | 保留既有窄版／展開測試 |
| `docs/07_guides/APPLICATION_MANUAL.md` | 新鍵盤操作段落 | 只移除本輪新增段落 | 不覆寫其他任務dirty文檔 |

前像與精確回滾紀錄在 `output/qa/recommendation_keyboard_fix_20261008_a/ROLLBACK.md`；不使用整檔checkout覆蓋其他未提交變更。
