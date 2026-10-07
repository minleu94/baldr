# Baldr M2 施工與驗證紀錄

本輪沿用[單一產品補完計畫](../superpowers/plans/baldr_product_completion_plan_20261006.md)的 P01／P02／P04 與使用者回饋，持續由 Luna Max 葉片實作、中央審核。本文件保存工程證據；M2、完整選股器、Native 真人與原計畫全部工作包仍未完成。

## 已完成的局部驗證

| 項目 | 證據與範圍 | 限制 |
|---|---|---|
| 全母體產製與既有父層 | 中央隔離回歸 `31 passed in 226.73s`；raw：`output/qa/baldr_completion_m2_20261007/producer_parent_root_1.log`。包含 17／257／1,000 檔、全排除、取消、跨新程序續跑、來源修訂拒絕與原 parent 測試。 | 這次程序載入的是長路徑整合前的版本；後續 I/O 修改須另重驗，不能引用此結果證明新路徑完成。 |
| 技術來源與封裝 | 中央 `52 passed in 6.73s`；raw：`output/qa/baldr_completion_m2_20261007/kernel_source_root_1.log`。17 項來源測試加 35 項封裝／版本測試，包含兩份 kernel 原件 SHA、缺件／篡改拒絕與合成 frozen 根。 | 合成 frozen 根只證明契約，未建置或驗證包含此 adapter 的新 exe。日期無效列的 SQL 邊界另在補強，須再驗。 |
| 受控保存 preflight | 明示 `ResearchCaptureWriteScope` 的來源不符、範圍外輸出、沒有 scope 的外部輸出皆拒絕，且未建立設定輸出根。 | 實際 17 股正常外部保存最初失敗；不能由拒絕測試通過推導正常流程可用。 |
| 長路徑與受控根整合完成 | 中央 `managed_scope_root_7.log`：4 passed；後續 `managed_engine_root_1.log`：80 passed、2 skipped，包含原 capture／parent、managed scope 與長路徑閉環。17 股兩批實際保存、全域查詢及新程序唯讀重開通過，來源 DB bytes／mtime 保持。 | 兩項 skip 為 Windows 一般 symlink 建立權限限制；hardlink 替換檢查實際執行。這是底層工程完成，正常 UI 產製／完整 query 收藏與新 exe 未因此完成。 |

## 正常研究保存的長路徑缺陷

原 capture writer 只允許 QA／Temp，無法支撐正常設定輸出根。新增明示 scope，派生 `{configured_output_root}/research_snapshots`，只允許其嚴格子路徑。來源 DB 以 query-only 開啟核對，DB／WAL 不得位於輸出根；沒有 scope 時原隔離限制保留。唯讀 writer 可重開既有保存來源，但必須在序列化、mkdir 或 lock 前拒絕寫入。

中央整合案例以合成 SQLite 產製 17 股兩個 batch，輸出在 repository 的 `output/ms<唯一識別碼>/research_snapshots`，刻意位於 QA／Temp 之外。沒有放寬 verifier，也沒有縮短測試根來掩蓋真實路徑問題：

1. `managed_scope_root_1.log`：快照已發布，capture 的最終 `capture.json` 路徑達 275 字元，Windows 寫入／讀回失敗。
2. `managed_scope_root_2.log`：capture I/O 修正後，父層容量掃描仍對深層普通路徑呼叫 stat。
3. `managed_scope_root_3.log`～`managed_scope_root_5_diagnostic.log`：只有在短 root 先轉 I/O 路徑仍不夠，深層路徑需要逐層轉換。FileNotFoundError 的實際呼叫位置另保留在各具名 Temp fixture 的 `io_errors.json`。
4. `managed_scope_root_6.log`：父層完成後，聚合 run 的段檔 temporary filename 再度超出 Win32 路徑限制。
5. 修正逐層 OS I/O 邊界及短 temporary filename 後，`managed_scope_root_7.log` 的實際產製／新程序重開全過；整合提交前另完成 `managed_engine_root_1.log` 的 80 passed、2 skipped。原失敗沒有刪除或改寫。

上述 raw 都位於 `output/qa/baldr_completion_m2_20261007/`。失敗研究輸出、partial、原始來源與診斷保留。擴展路徑前綴僅用於 OS I/O，不寫入保存 identity、manifest 或使用者設定；容量、連結、來源 hash、取消與原子發布的守衛均須維持。

## H20 下鑽查核

新測試走保存來源、公開 cohort reader、股票選取、exact cohort 再驗、MainWindow、實際報告 service、TaskWorker 與公開 H20 reader。使用合成研究來源，模型 contract port 的隔離邊界另明示，沒有訓練或偽造完成的 fit 收據；因此不稱 canonical 模型全鏈驗收，也不取代使用者原 2382 的 Native 驗收。

一次觀察 wrapper 的 `**kwargs` 改變 signature，導致 TaskWorker 注入取消參數再轉送給原函式。加上 `functools.wraps` 後該問題消失，**已撤回 production 缺陷判定**；沒有因此修改正式 reader API。

最終 `tests/test_ui_qt_h20_saved_source_journey.py`：2 passed in 246.84s，原 log `C:/t/h20journey_20261007_final2.log`。成功路徑決策日 10/6、來源日 10/5、特徵日 10/2，各自核對 report／context／H20 evidence；摘要顯示 +12.34% 保存預測、未扣成本及自然結果尚未成熟。詳細 label 位於預設折疊的來源區，驗可見性的是首屏五問結論及狀態 panel。

報告 service 失敗時，H20 reader 目前不會啟動，原因在狀態／限制可見；這項測試只證明現有失敗行為，不能宣稱有效 H20 可獨立於一般報告失敗呈現。一般價格列不混入保存 H20 context 是既有來源隔離政策，不能由 `price_points=()` 判定 H20 原件不存在。使用者原 2382 畫面與開啟版本仍待核對。

## 仍須完成

受控根的底層產製→完整 run→全域查詢→新程序重開已在具名隔離案例通過；接著仍須正常 UI 的產製入口、完整 query 的收藏／比較／返回，以及新 technical 保存版本。原 v2／v3 產物不可事後補欄或套新公式。新固定來源候選需另做 Python／exe 同版驗證，既有候選與正式 exe 保留。

目前未讀寫正式市場 DB、未更動私人模型／持倉、未觸發 Task、未交易，也未 push／更新 main／取代原 exe。真人驗收入口沿[推薦回饋 QA](BALDR_RECOMMENDATION_HUMAN_FEEDBACK_20261007.md)；目前不要求使用者重複驗尚未完成的 M2 流程。
