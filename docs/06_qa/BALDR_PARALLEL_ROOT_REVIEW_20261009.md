# Baldr 並行工作 Root 審查補記

本次審查延續原補完計畫，未縮減全母體、H20、實際 UI 與同版啟動驗收的範圍。

## F03 收集模組

Root 實讀 `daily_market_technical_universe_kdj_alignment_query_v1.py` 的來源要求、builder 綁定、parent 收集、有界 entry 與 projection group。新模組明示未核資格，尚不能據此宣稱 full-N 查詢、資格發行或 UI 完成。

Root 執行：`.\.venv\Scripts\python.exe -m pytest tests/test_daily_market_technical_universe_kdj_alignment_query_v1.py -q -o addopts=`，結果 `9 passed in 0.67s`。此結果只涵蓋當時的九項合約測試。

待 owner 補證：公開來源要求建立時立即執行 byte budget；任何來源、順序或取消失敗後的終態行為；取消回呼後續回傳 False 時仍不得續收集。Group 在 try 區塊外執行的取消與前置核驗也須納入失敗終態，不得把部分收集重新包成完整資格。

後續 owner 加入建構時大小檢查與公開操作失敗終態。Root 再實讀 wrapper、group `_poison` 及取消恢復負例，重跑同命令得 `10 passed in 0.59s`。目前 group 失敗會使 KDJ member 拒絕讀取未核 entries，但 MA member 仍可被取得；未來完整來源資格發行必須檢查 group 終態、禁止任一 member 獨立發行部分結果，並有實際 full-N 負例。本次純合約通過不代表該原子發行邊界已完成。

Root 後續逐段閱讀 compact entry 與 consume 的日期、snapshot object 身份、source clock、method、parent row 對照及 Decimal leaf 投影。凍結 SHA 已核一致：module `c0c3bb9fd17d9c25ce5476a4a4bfaececf976d1affff79a51ef5f3c215b275c2`、test `9a398c3d8b10d3c61e91d1d216116f92bb43e1cfeb93ab71ee0197b81e9ceaeb`、plan `b0300581719683656151172ed919bf9491578808a20dce9e9755c72da4a3c0a4`。兩檔 scoped mypy 無問題。

尚有公開建構界限缺口：request/entry 的建構檢查只計 body bytes，實際 `to_dict` 還會附 identity 欄位；collector 雖再次檢完整 entry，公開 DTO 本身仍可超過宣告上限。已要求 owner 保存此凍結版本，再按最終 canonical payload 的大小統一檢查，新增 body 未超限但完整 payload 超限的負例。上述 SHA 是本次審查版本，不能冒稱後續修正版本。

大小修正已完成並經 Root 實讀：SourceRequest 檢含 identity 的完整 16 KiB payload；CompactEntry 建構與序列化均檢完整 payload，collector 繼續按完整 bytes 累計。兩個新增反例分別使用真 request 邊界與縮小的 entry 測試 budget。Root fresh 結果 `12 passed in 0.63s`、兩檔 scoped mypy clean。新 SHA：source `3afb98f39a7b2a66a43f1796edd8255c155940a08b24c11effdddc14e9b9e9a0`、test `054b975a51779e4cd9ad9f01efd6cdf5039609c90f0d139877f467c9f73ee367`、plan `4d0f3b1827398f5361ece9ea612b03220e5fa103deab87e2ca7692408253ec89`。接受的範圍僅為 bounded unqualified skeleton，原全母體發行與查詢 gate 仍待完成。

## H20 隔離測試接線

Root 拒絕僅以 finally 還原共享 `_case_root` 作為並行安全證明：其他來源或 archive 核驗呼叫仍可在暫改期間讀到 QA root。

已允許 owner 製作 cloned globals 的隔離小測試候選。原模組 globals 必須不變，clone code 使用凍結原函式，globals 差異逐項明示。此為受控 runtime 差異，不代表原 runtime 完全相同；若既有資格核驗要求原 globals 身份，應保留失敗，不得繞過。

完整 Main 尚未因此獲准執行。須先有真凍結 guard 正例、主失敗保留、假根與來源拒絕，以及並行原 helper 仍使用原 case root 的證據，再由 Root 審查 diff、pins 與啟動封套。

Root 已實讀 E 候選的 clone 實作：原模組 globals 不改，私有字典的差異為 `_case_root`、`_plain_runtime_sqlite`、`_install_sqlite_allowlist` 三槽，helper/installer 沿原 code object 執行。仍需補 runtime 持續核驗：固定所有非差異 globals 的 object 身份及 keyset，並核安裝後 `sqlite3.connect` 的 exact wrapper 身份與 scoped globals；只在 receipt 記錄布林不足以拒絕 resolver 替換。已交 owner 增加具名拒絕與相應負例，未授權 Main 啟動。

## 分工與真人驗收

三條子任務持續獨立推進：H20 接線、F02 查詢續驗、F03 KDJ 收集與整合準備。Root 負責交叉審查。尚未產生通過整合驗收的新啟動版本，因此本次沒有新增真人重測要求；後續交付應提供實際啟動位置及同版本驗收步驟。

Root 已再核目前推薦 view 與 layout test SHA，分別仍為 `5F0FAA96F246C62C7693E1771D538D88B72AE95A6544208D74B14650ED16EDD5`、`61E4ECAF7F4E339798C73950808D5CB17B4F03B9A23B8C1B73DF48C33C340701`，與先前 11 項 layout suite 的受測版本一致，因此沒有無理由重跑此套測試。此一致性仍不證 EXE 同版驗收。

Root 補驗 H20 未知列的兩個現有案例：`pytest tests/test_ui_qt_personal_h20_research_widget.py -k unknown -q -o addopts=`。首次 sandbox 執行在合成 capture 的 `os.link` 遇 WinError 5，兩項均尚未進入 UI 斷言，不視為產品結論。改用新的 native 隔離目錄 `C:/t/h20_unknown_root_20261009_7c41`，同兩項測試 `2 passed, 11 deselected in 2.13s`，terminal exit 0；JUnit 保存於 `output/qa/h20_unknown_root_20261009_7c41.xml`。覆蓋未知列禁止下鑽、完整可複製來源原因與恢復原 pin 的前置條件；不覆蓋原 2382 的來源修復、效能、Main 或 EXE。

真人草稿入口名稱亦已對照目前原碼：「研究選取股票」、「摘要」、「返回來源清單」、「收藏此原排名研究」、「個人 H20 原保存研究收藏」、「重新整理收藏」、「重開所選 H20 研究」均有實際控制項。H20 表格的可下鑽狀態是「可核原預測」；「未知」列會顯示可複製核驗原因且停用研究按鈕。未來啟動候選應先由工程驗證原 2382 列可核，不能把未知列停用交由真人反覆點擊排錯。
