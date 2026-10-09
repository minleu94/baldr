# 根目錄殘留檔案盤點

2026-10-09 Root 以 Git 未追蹤清單與檔案屬性盤點。此輪沒有移動、刪除或覆寫任何檔案，建立時間不能證明建立者。

| 根目錄未追蹤檔案 | 正式位置或後續處理 | bytes |
| --- | --- | ---: |
| `reason_engine.py` | Git 已追蹤 `decision_module/reason_engine.py`；兩者 SHA 不同，先審差異 | 21098 |
| `recommendation_service.py` | Git 已追蹤 `app_module/recommendation_service.py`；兩者 SHA 不同，先審差異 | 218965 |
| `presenter.py` | 存在 `ui_qt/views/recommendation/presenter.py`，需比較內容確認副本身分 | 32859 |
| `test_r019_reason_regime_parity.py` | Git 已追蹤 `tests/test_r019_reason_regime_parity.py`，需比較差異 | 27299 |
| `test_recommendation_view_presenter.py` | Git 已追蹤 `tests/test_recommendation_view_presenter.py`，需比較差異 | 8351 |
| `supervise_f02_ma_composite_257.py` | 名稱指向一次性 QA supervisor；需核對引用與 owner，歸檔位置為 `output/qa/` | 69649 |

前五項建立時間皆為 2026-10-08 15:57:32（本機時區），supervisor 為 16:14:49。針對 `app_module`、`decision_module`、`ui_qt`、`scripts`、`tests` 的 Python 檔搜尋裸 `import reason_engine/recommendation_service` 與 `from ... import`，沒有匹配；這不是全專案動態載入不存在的證明。

## 整理 gate

先查完整引用與實際內容差異、確認不是其他 agent 仍使用的未提交成果，保存可還原的 SHA 與備份，再把必要改動整合到正式位置、將多餘 QA／副本移至已排除的備份位置。不得直接以根目錄副本覆蓋正式模組，不得為清空 working tree 刪除來源不明檔案。此盤點不代表整理已完成。

## 差異與備份進展

Root 實讀兩個服務完整 diff：正式 ReasonEngine 支援 `max_reasons=None` 保留全部理由，根目錄版本僅支援整數上限；正式 RecommendationService 使用全部理由，根目錄版本限制三個理由並取舊 canonical reason text。根目錄版本不是較新的待整合實作，不能覆蓋正式版本。

其他三份前像相對正式檔的 diff stats 為 presenter 3 insertions/129 deletions、reason parity test 18/44、presenter test 3/112；仍需讀其完整差異才能完成整理判斷。全專案非 output 的文字搜尋未找到指定根目錄檔案的 Python 直接啟動指令；supervisor 名稱僅見 QA 文件的版本化 output 路徑與盤點紀錄，未證明不存在動態引用。

三條目前工作線均回報沒有使用這六個根目錄檔案。已將全部六檔複製到 `output/qa/root_residual_backup_20261009_b/`，每檔 source before/after SHA 與 backup SHA 三者相等，清單存於該目錄 `inventory.json`。原檔仍在原處，尚未移除；正式來源與其他 agent 的未提交變更未被覆寫。
