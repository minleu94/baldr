# 原保存 2382：一次實際旅程計時方案（尚未執行）

本方案補原使用者回報的首次名單與單股約二十秒等待；合成測試的耗時不代表這份來源。只執行一趟，不清系統快取、不預熱、不稱為 cold benchmark 或 p95。完成條件包含實際資料身分、原生 worker 收尾及返回狀態；僅有時間數字不足以驗收。

## 已核來源與待固定設定

2026-10-10 root 唯讀確認 `D:/Min/Python/Project/FA_Data/personal/recommendation_h20/activation.json` 存在，697 bytes，mtime UTC 為 `2026-10-06T16:41:29.1028539Z`。其保存內容為 enabled=true、revision=1、scope=`personal.default`、candidate/model=`rec-cal-3f8b2c276ef316e28de3806d`；這是配置存在證據，尚未證明 2382 列或來源可用。

該 activation 的 fit receipt 指向 `C:/Projects/PythonProjects/technical_analysis/output/qa/pc-fit-v7/fit-v7-fe4e918b1257.receipt.json`。下一步需核這個小檔及沿途是否為連結、讀取契約是否接受；不能修改 activation 或原收據來避過拒絕。

同日 root 獨立核小檔：activation SHA-256 為 `769a40ba527c0c6d845349ef4f1002f9845ff6f68f5c3695800aee863c62ad3f`；`h20_product_reference.json` 為 623 bytes，SHA-256 `a2f2dbcf4c7cc70d212f37147cc465546748ea83cd03864d148e66b8abe319fa`。其指定 manifest 為 5,057 bytes，SHA-256 `a2cad4b3ac8ff978f52ecb28d006da37573cd1313efcee28bfc1d5d632661e76` 與 reference 相符；completed、decision_date=2026-10-07，十檔中 2382 唯一，captures 中也有唯一 2382 的 sample／prediction／path／raw SHA。尚未讀 capture 或大型 SQLite，不能因此授予 available、PIT 或正式用途資格。

子代理唯讀確認上述 fit receipt 存在、沿途無 reparse/Junction；尚未讀其內容。實際使用者 `C:/Users/archi/AppData/Local/baldr/config.json` 的 DATA_ROOT／OUTPUT_ROOT 對應 D 市場根／其 output。沙箱 shell 的 LOCALAPPDATA 與 GUI 不同，量測 runner 必須明示 BALDR_CONFIG，不能用目前 shell 的預設宣稱與真人同設定。

`MainWindow._personal_h20_configuration()` 以 `PERSONAL_H20_ACTIVATION_CONFIG` 覆蓋，否則使用市場根的 `personal/recommendation_h20/activation.json`。必須核 bootstrap 的實際市場根與覆蓋值，不能從 ML research storage 猜 H20 根。現用 `output/ml_research_storage.json` 的 `active_root` 為 `D:/Min/Python/Project/FA_ML_Research`，用途與上述 activation 不同。

測量前還需固定：目前程式版本／來源 pins、原保存 reference／manifest、一般報告的 DATA_ROOT／OUTPUT_ROOT、2382 的 available 列身分與決策日。若原列不存在或 unknown，本次應如實留下失敗／未知，不能換股票、改日期或換成合成來源取得成功。

## 四段分開計時

| 段落 | 真正操作與結束點 | 必須保留的證據 |
|---|---|---|
| 首次名單 | 選 H20 頁籤／讀取保存名單 → worker 結果正式套入列表 | action→列表 ready、worker 時間、每個來源群組 copy/hash/開啟/manifest/capture/終態重驗進度與 bytes；initial/terminal 一致；副本清理與 native finish |
| H20 下鑽 | 對 2382 真雙擊 → H20 evidence／chart 投影發布 | context、reference、capture、列身分一致；區分已核 cohort 投影與 fallback 完整重讀；chart unknown/partial 不算 available |
| 一般個股報告 | 同次 context → reportLoaded／畫面 render | 獨立 report worker 時間及截止日；它與 H20 worker 並行，不把它的等待歸因於 H20 重核；整頁 ready 另報兩者較晚者 |
| 返回來源 | 真按返回 → 原列／原名單恢復 | 同 cohort/view/reference、2382 原選取、無第二次完整 cohort operation；fallback 全重讀另列；原生 finish 與 worker registry 收尾 |

同次已核 view 下鑽與返回，應使用 `project_personal_h20_verified_cohort_selection_with_chart_reference`／既有 reference recheck 路徑。若實際改走 `read_personal_h20_product_for_stock_with_session` 或重新 `_refresh_personal_h20_cohort()`，保留為另一條路徑，不能宣稱重用成功。

## 副本與量測邊界

- 新測量副本及收據使用 E 槽全新短、plain、與原來源不重疊的具名目錄。產品 `PersonalH20SQLiteReadOperation` 自行建立、核驗及清理副本，不手工先複製大型 SQLite，不新增 C 槽大型副本。
- `PERSONAL_H20_SQLITE_READ_ROOT` 經現有 bootstrap／TWStockConfig 傳入；不能用測試 monkeypatch 讓 reader 跳過原 pin 或來源重驗。
- 不提前掃大型 SQLite SHA；來源起訖一致由本次 operation 的原核驗及檔案身分證據取得。系統快取狀態標為未知。
- 一般報告的 OUTPUT_ROOT 若改成空隔離根，會改變其 freshness 等輸入；該耗時不能冒充原配置。需先列清只讀輸入與所有可寫狀態的隔離路由。
- 不保存收藏、不更新行情、不產製新名單、不訓練、不改排程或真帳本；無網路。單次 runner、寫入清單、有效環境與終態收據 schema 交 root 審查後才執行。

## 驗收與目前狀態

成功須同時證明原完整名單核驗、2382 原身分、H20／chart 實際狀態、一般報告獨立 endpoint、精確返回、來源前後不變、副本清理及所有 worker native finish。四段耗時分開公布；若某段失敗仍保留其真實終態。尚未訂新的產品速度達標數字，本方案不降低原計畫的效能門檻。

目前：配置小檔已定位；原列／manifest／來源資格、一次真旅程、Native 真人及新 EXE 尚未取得。既有合成 MainWindow 測試只用來證明操作契約，不能替代本方案。

程式依據：`ui_qt/main.py` 的 H20 configuration、refresh、request、saved-product read、return 路徑；`scripts/scheduled/personal_h20_daily_hook.py` 的 cohort／verified selection；`data_module/pinned_sqlite_read_session.py` 的 snapshot／終態核驗；`ui_qt/views/stock_research_report_view.py` 的一般報告 worker／reportLoaded。

接續入口：[完整產品計畫](../superpowers/plans/baldr_product_completion_plan_20261006.md)、[目前 root 證據](BALDR_F03_PREPARE_ROOT_FOLLOWUP_20261009.md)、[合成來源真人六步](BALDR_COMPOSITE_HUMAN_CHECK_20261010.md)。
