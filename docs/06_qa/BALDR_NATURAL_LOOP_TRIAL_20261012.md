# 2026-10-12 個人 H20 自然迴路試跑

## 範圍與原問題

人類授權試跑、修正工程錯誤、更新文件與 commit；既有唯讀 automation 的時間、目標、啟用與通知不變。本輪不改 Windows Task、不回填歷史、不抓行情、不交易、不 promotion。真來源試跑只讀正式來源，模型與自然輸出保存於新建隔離私人根及 ignored QA output。

本輪來源回讀顯示 G9 current-observed capture 僅有 10/6（10 檔）、10/12（16 檔）；自然 H20 未成熟。10/7 有 same-run raw cycle 阻擋、10/8 source wait deadline exhausted；10/9 官方國慶補假、10/10–11 週末。個人 activation 的每日 manifest 僅讀到 10/7。不能因此宣稱每日模型證據一直正常累積，也不能將漏日當成熟等待。

原真來源 smoke 重現 `exact_completed_nonfuture_cohort_required`：G9 推薦 eligible 16 檔與同次 G6 terminal 中央 10 檔不同。保留原完整母體 guard，改 caller：中央 H20 依 exact G6 terminal 完整 `current_symbols` 建自己的來源、daily、entry、outcome lane；不將固定 10 寫死。一般推薦 lane 不登記新個人 H20 entry，但保留舊 captures 的個人自然結果掃描。

## 來源及防未來函數邊界

- 正式來源 `D:/Min/Python/Project/FA_Data`；G6 research `D:/Min/Python/Project/FA_ML_Research`；G9 shadow `D:/Min/Python/Project/FA_Data_Shadow`。
- G6 run／cycle：`raw-pit-20261012T120503297513Z-38512-4fb13c31a4e54359807c666c778281d5`。
- terminal：`D:/Min/Python/Project/FA_ML_Research/current_stock_cycles/2026-10-12/2f8841e8abda9b545c0af1e26804ddcd/terminal_receipt.json`；SHA `sha256:af6b286d8ecbfe230b092bc2a30cdb986e39b5b850bf1667907dcad4ffe01191`。
- 中央母體：1225、1256、1465、1477、1560、1714、1721、2382、3207、9935。
- 原 activation candidate `rec-cal-3f8b2c276ef316e28de3806d`；原 fit receipt SHA `sha256:f5ca4372ba71ac3c006181ab0dcd4e2a56fdc62ba6529083cb63bbc7987a35b1`；原 contract `sha256:185a2378794a01c4f627d64b158e2fd50c6f41700af0ccbb3e31cfc60aa17053`。

使用實際 UTC／台北觀測時鐘與 public source verifier，不倒填 10/12 收盤後預測。試跑當下台北已是 10/13 盤前；當日 entry 尚未有 close 或 H20 未自然成熟時應 pending。所有 terminal/run/hash、完整母體、來源時點與原 frozen model guard 保留；不新增正式 PIT、technical prospective、cohort 或 promotion 資格。

## 測試收據

本機原件位於 `output/qa/natural_loop_trial_20261012/`，依 Git 排除規則不提交。每次 QA 使用 Windows owned Job（8 GiB、12 processes）、workspace mutex、可用記憶體 precheck、suspended assign-before-resume；terminal 後核 Job0 並關閉 handles，串行執行。

第一次中央真來源試跑 `central_1791830845915170200` 在本 QA 工具原 240 秒上限中止，Job0／handles closed，部分預測保留；不是完整通過。後續中央試跑採現行 G9 wrapper child 3600 秒期限（wrapper 整體 14400 秒），不改 producer 設定或資格。

初次修正迴路回歸 `loop_1791831199154302000`：173 passed、1 skipped，exit0、23.328 秒、自然 Job0。補加舊 captures 掃描防回歸後重跑 `loop_1791832182972977400`：174 passed、1 skipped，exit0、15.843 秒、自然 Job0／handles closed。

真來源終態 `central_1791831232929492400`：exit0，892.437 秒，自然 Job0、handles closed、未強制清理。業務報告 `smoke_1791832124977692200.json`（SHA `sha256:f37fb95a4627bc2c8b08735654a987a5295bab560367d8fee7b8f2f3f3ca1bc9`）記錄 PDT 11:53:54–12:08:44、台北決策日 10/13，10／10 個原模型 predictions、完整 daily manifest、自然 batch 已核驗。manifest SHA `sha256:273456dddd0febed949e703ed4df2273ef830f369a0328130f29a7941bb2ffc1`，保存於新建 `C:/Users/archi/AppData/Local/Temp/h20trial_c6qtygn8/h20_daily_receipts/`；原 activation／fit receipt／G6 terminal raw SHA 前後均相符。

結果為 `completed_with_pending`：daily `effective_model_run=true`；entry `same_date_entry_session_missing`（上述10檔、10/13、H20），自然 batch `completed`、pending10／matured0；尚無合法 entry，natural research 為 `no_current_observed_input_captures`。這是盤前等待，不能發布 entry binding／matured join。完整 entry→成熟／缺價／hash拒絕等路徑由隔離回歸驗證，真來源仍須等實際當日收盤及自然20交易日，沒有用合成價格替代。

最終 G9 主迴路回歸 `learning_1791832214405311100`：40 passed、exit0、77.735 秒（含隔離自然累積、漂移與回滾）；不代表實際市場已有成熟結果。mypy 兩來源、py_compile 五檔、quant guard 均 exit0，收據分別 `types_1791832315572739500`、`compile_1791832322959455800`、`guard_1791832325008152500`，均自然 Job0／handles closed。git diff whitespace 檢查通過；本輪沒有 UI 修改。

## 後續排程驗收條件

G9 `personal_h20_natural_lane` 必須有完整中央母體的 exact daily manifest／prediction hashes；同日合法 entry 擷取後登記 exact manifest／capture SHA；後續由原自然 outcome verifier 與20-session projector讀回。當日缺價須列股票／日期／horizon，漏日不重建；未成熟不視為工程失敗。新的 captures／outcomes 沿 `personal_h20_natural/recommendation_learning/`，歷史 captures 仍按舊根與原 binding 核對。

Paper 10/12 EOD 的 `daily_prices.open:1435`、formal source revision release 及其他 producer qualification 缺口不因這個 H20 修正而解除。今天實際 Task 全鏈完成仍需按 Runbook 的同次 receipt／hash／clock 回讀，不能拿隔離試跑取代正式排程驗收。
