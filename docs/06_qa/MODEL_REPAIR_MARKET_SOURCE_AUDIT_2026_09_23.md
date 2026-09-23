# 模型完整重訓後的大盤來源差異（2026-09-23）

## 判定與範圍

H5 v2 完整 fit 已完成，但市場特徵組的 heldout 風險預測大量偏高。獨立核對發現 `market_indices.成交量` 混用兩種來源，且 TWSE FMTQIK 分支以收盤指數代填開／高／低。這是資料語意問題；目前證據不能把 Yahoo 的 Volume 一律乘上 1,000，也不能把指數後期的正常漲幅判為錯價。

本次來源查核只讀取 run02 快照與官方月報，沒有修改正式 SQLite、封存模型或 v2 資料。官方歷史來源已核驗，bounded 新資料、fit、獨立評估及當日推論已完成，但品質未勝簡單基準；全量 H5 v3 仍在建置，因此不能宣稱「完整修復已驗收」。各階段紀錄如下，以最後完成證據為準。

## 已核對的證據

- v2 對訓練日期截至 2025-10-23 且超額報酬 label 非缺值的 3,107,517 列做描述性掃描。市場成交量有效值 3,091,009 列、範圍 0–14,999,500；heldout 自 2026-05-20 的 144,088 列全部有效、範圍 8,082,548,083–19,686,100,251。前者是診斷日期切片，不冒充 trainer 的精確 maturity fold 3,100,743 列。
- run02 的第一筆成交量大於 100,000,000 的 TAIEX 記錄是 2025-12-01（7,418,235,597）；2025-11-03 保存 3,968,500。這只是可重現的來源斷點，不用硬編碼門檻決定所有未來資料是否合法。
- `data_module/data_processor.py` 直接將 Yahoo `^TWII` 的 `Volume` 改名為成交量；`data_module/data_loader.py` 的 fallback 同樣保留 Yahoo Volume。正常 TWSE FMTQIK 分支卻把「成交股數」存入同欄，並把「發行量加權股價指數」寫入開／高／低／收四欄。沒有欄內來源與單位一致性證據。
- 官方 2025-11 月 FMTQIK 回應顯示 11/03 成交股數為 **8,299,689,369**、收盤指數 **28,334.59**；與 SQLite 3,968,500 並非可直接視為相同的量。官方同月 MI_5MINS_HIST 顯示該日 O/H/L/C 為 **28,253.53／28,494.99／28,150.45／28,334.59**，可取得真實開高低，不需要以 close 代填。
- 全量 H5 市場組的 heldout 預測 MAE 頭誤差 **9,546 bp**、基準 **322 bp**；raw downside Brier **59,807,451 bp²**、基準 **22,651,676 bp²**。這與來源斷點同時存在；未做逐特徵因果消融前，不宣稱每一項誤差都由成交量單獨造成。

官方資料：[FMTQIK 月報](https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date=20251101&response=json)、[加權指數開高低收月報](https://www.twse.com.tw/indicesReport/MI_5MINS_HIST?date=20251101&response=json)。這是現在取得的歷史回應，不是歷史當日已保存的 PIT 證據。

## 可追溯產物

整合工作區 `output/qa/model_repair_review/` 保存 `full_h5_market_feature_diagnostic.json` 及 `market_source_probe_202511/` 的兩份原始回應與 receipt。FMTQIK 在 `2026-09-23T07:46:26.398947+00:00` 取得，檔案 SHA-256 `480173e3b0068a3c9070bbd7762bdfa2951a1a4a88b8443af90b46ec940f4565`；MI_5MINS_HIST 在 `2026-09-23T07:46:51.778898+00:00` 取得，SHA-256 `c8eaf1c5221819503018cdfba06caf71fca845a75e3a40598d77afb11aea78de`。兩份各 20 個交易日、日期欄與報表月份相符。

## 後續修復界線

先封存涵蓋訓練區間的兩種官方月報，逐日核對 close 與日期、明確綁定成交股數單位和真實 OHLC；取得日保持實際日期。接著評估新研究資料版本需重算哪些市場特徵與 benchmark labels，再重訓受影響模型。保持 62 欄順序／scale、normalization、模型輸入契約及 15 個重構凍結檔不變；來源值修訂必須有新的身分與差異證據。原始資料、v2 模型及其評估保留，不修改 heldout 或混寫正式來源。

## 官方來源驗證入口

新增純唯讀 `data_module/ml_restatement_official_market.py`。`load_official_market_capture` 要求明確清冊路徑、檔案 SHA-256 與實際 `as_of`，逐份重新讀取月報而非信任清冊快取列；檢查連續月份、兩報表逐日 close 一致、真實 OHLC 範圍、成交量值為整數、檔名／官方 URL／bytes／SHA、取得時間與臺北日期截止。實際來源不足會失敗，不補 0、不推算固定倍率，也不以收盤代填 OHLC。未知的漲跌百分比仍保留缺值。

初版擷取工具在「所有官方報表已成功、但原 SQLite 包含非官方交易日」時也回報 incomplete；reader 只允許這個明確原因，仍需所有月份的兩份原始回應、來源 hashes 和 cached rows 全部一致且 failures 為空。它不把這個相容處理套到既有 dataset／模型 gate。

Focused tests **24 passed**，涵蓋格式錯誤／非整數成交量、跨月／重複日期、偽造快取、兩報表 close 差異、重新 hash 後仍不一致、URL、時鐘、缺報表及截止日後資料不被消費。單檔 targeted mypy、兩檔 py_compile 通過。這只是來源 reader 的驗證；全區間封存、修訂資料建置及新一輪模型 fit 尚未完成。

2014-01 官方回應亦顯示 source 值差異：1/2 正確 open=8,618.60、close=8,612.54；run02 的 open=8,612.5、close=8,618.559542，數值接近互換但不精確相同，尚未定位最初寫入事故，不能概括所有年份都只是兩欄互換。初步交易日對照另見原來源有 2014-07-23、官方月報無該日，官方有 2014-12-27、原來源缺該日；須按官方完整交易日重新推導 label horizons，不能只替換成交量或保留錯誤 benchmark labels。

本輪前一批文件 commit `aeaaef9a` 已合入 dev `fbc4047b`。整合前後 195 個其他工作 dirty 檔中，194 檔 bytes 一致，R011_IMPLEMENTATION_REPORT.md 在 owner 同時工作期間變動且不在本批任何修改路徑；index 空。未將該 owner 變動暫存或回復。

## 全區間來源與 v3 重建驗證

2014-01–2026-09 共 **153 個月、306 份**官方回應已全部成功封存、逐份重驗，消費截止日為 **2026-09-22**。官方兩份報表共 **3,105 個交易日**；對照 run02 的 3,088 日，原來源多出非官方日期 **2014-07-23、2016-07-08**，漏掉 **19 個**官方交易日。清冊位於 `E:/codex_model_repair_20260923/market_sources/official_monthly_v1/capture-20260923T080139Z.json`，SHA-256 `4bc1917cbbc46334b10b40012d569d63db4084bae8e17972d46795bf01c8839f`，封存完成鐘 `2026-09-23T08:01:39.776960+00:00`；初版工具的 incomplete 僅指上述兩個原日曆日期，報表擷取／解析 failures=0。

在共同的 3,086 個日期上，依官方兩位小數精度比較後，O/H/L/C 分別有 **2,898／992／994／2,701** 日不同；最大絕對差分別 **2,562.81／2,562.81／1,665.94／1,152.04** 指數點。這些是來源差異計數，不是股票跌幅或投資損失。正式 `meta_data/market_index.csv` 的 3,088 日、五個 OHLCV 欄位與 run02 全部一致，CSV hash 前後均為 `fe407fc4bd23c5ca61e6bfff094b84c8db5314f7eb83e22f149e1d417c023c00`。因此不能藉由重匯相同 CSV 修好來源。完整差異保留在 integration `output/qa/model_repair_review/official_market_full_source_comparison.json` 與 `official_market_precision_and_csv_comparison.json`。

新增 `data_module/ml_restatement_research_dataset_v3.py`，沿用既有完整股票前綴、62 欄、原 targets、成本與 Decimal label 公式，市場資料和交易日改用核驗官方來源。既有 baseline rows 保留；不是官方交易日的決策列無成熟 label，不把它變造為有交易。每個 horizon 重新算結束日及股票／市場報酬，不能只改最終 excess 數值。`source_revision_id` 保留為股票 SQLite 修訂身分，官方市場來源以額外 manifest／SHA 獨立綁定；新資料、程式依賴、時鐘、日曆皆進入 v3 identity。

Builder 開始即保存外部 `source_start.json`，結束重新核對程式、快照和全部官方月報，成功才發布 dataset manifest 與 `model-repair-source-custody.v2`。這次確實有 start evidence，不沿用 v1 sidecar 的「未觀察到開始」敘述。原 builder 僅抽出清冊產生方法並補齊型態；數值公式不變。45 項相關 tests、兩檔 targeted mypy、三檔 py_compile、兩項量化 guard 通過。

真實四檔 2014 年樣本 **668 列**已完成，輸出 `E:/codex_model_repair_20260923/dataset/official_market_v3_sample_2014_run01/manifest.json`，file SHA-256 `61607aab068cbd8f5833b7c5280e2fc7eff38aababfc6e4c7a6b0dd659855d05`。Root 對照 v2：**32,732 個**非市場特徵 slot 及 masks 完整一致、targets／stock events 保留；668 列市場特徵有改變，H5／H10／H20／H60 的 labels／mask／結束日分別有 **660／664／664／665** 列改變。另直接讀股票快照與官方價格、以獨立 Decimal 算式驗算 **2,308 個**非缺值 excess／downside labels，全部一致；所有 label horizon 符合官方交易日。證據為 `official_market_v3_sample_independent_comparison.json`。

上述是來源及 v3 builder 的有界驗收，不代表新的完整資料、兩家族重訓或 current consumer 已完成。v3 必須先經支援此來源契約的 loader／外部 custody 驗證，不能手改 schema 為 v1/v2 來繞過拒絕。

## v3 訓練與當日 consumer 接線

H5 loader 現在依固定 v3 identity 欄位核對原始官方回應，保留 62 欄／scales、原 targets 與新增列缺值。custody v2 會讀回建置前保存的 source_start，核對實際開始／完成鐘、來源與六份 producer 原始碼；不杜撰 git commit，也不放寬舊 custody v1 的「未觀察到開始」契約。實際 668 列樣本已完整載入，外部 custody 驗證通過。

兩條當日研究入口增加官方來源相容檢查。新的 current capture 綁定官方市場 contract、原始報表與新股票 read transaction 前綴；新的月份可以另給 manifest/hash，不能使用舊混合單位市場輸入。13 檔真實股票（含 1256／1477）已以固定 run02 股票快照和官方月報完成新擷取／prepare，feature as-of 為 2026-09-22；這是輸入預檢，尚非新 v3 模型推論。當日 manifest file SHA `2b95f7c52f8587f7565bddb1f50ed95298596666442de46ec809d48e42e3158f`，identity `184d8ce5446258318a4757851180745280c445bd228028ac1081d61390c77391`，prepare 實際鐘 `2026-09-23T16:28:05.361200+08:00`；路徑與證據保留 integration `output/qa/model_repair_review/official_current_preflight.json`。

相關回歸先跑 88 tests 全通過，再加入官方來源優先於 SQLite／缺 contract 拒絕的實例，current capture 六項 tests 全通過（新增一項、其餘五項重跑）。九個變更模組 targeted mypy（follow-imports=silent）通過；包含依賴的檢查另回報兩個未改動檔的四項既有型態錯誤：technical_indicators.py 三項 TA-Lib enum、update_service.py 一項 normalized annotation。這批沒有修改那些檔案。

全量 v3 從固定 producer commit `56fc40be` 的獨立工作區執行，開始 `2026-09-23T08:15:12.906022+00:00`、來源核驗完成 `08:15:16.387440+00:00`；此處 consumer 修改不動正在執行的 producer。輸出為 `E:/codex_model_repair_20260923/dataset/full_restated_official_market_v3`，未加 row/date/symbol cap。此更新時仍在執行，尚無完整 v3 manifest，兩家族新模型尚未完成；正式資料、15 個重構凍結檔與 production pointers 不變。

## bounded 官方市場修訂入口

新增獨立 `bounded-allocation-official-market-restatement.v1`，父清冊固定為已修復股票前綴的 bounded v2。13 個市場／相依品質欄改取官方來源，其餘 49 欄（包含原先 25 個股票修訂欄）、targets／state 保留；股票修訂欄維持原先真正 availability，不能重新蓋成本次市場 clock。四個 horizon 重新使用原 Decimal／整數 bp 算式，不能只換 benchmark excess。

新日曆可能改變公司事件是否落入 horizon，故重新核對原 bounded 綁定的官方事件清冊，SHA `d9011aadde6902b04481252ffad445604366c576d0b9840a59e528492de2c69b`（`official-market-events-d51d54fa09f8f7e03f9d7fbd`）；依本次真實取得時間計算 label-only exclusion。它與 H5 使用的 corporate-action-adjustments 是不同來源契約，不交叉冒用。缺完整四個價格路徑、非官方決策日及事件交叉列會列入具名排除紀錄，保留原檔。

既有 v1 bounded consumer 的「只有 210 個 H60 修訂且不進原 folds」規則維持；新 profile `restated_official_market_event_maturity.v1` 明示所有 horizon 的實際修訂鐘，保留原四組日期窗、按新標籤成熟日重新選樣，另外回報每個 fold 中的修訂標籤數量，始終 historical_pit／formal_oos／production 為 false。registry 僅允許原 20 個技術來源與新 8 個市場來源定義修訂，62 欄名稱／順序／scale 不變。

七項新增 tests 驗證 Saturday horizon、真實 open、缺價拒絕、公司事件排除、四 horizon 的修訂鐘、新舊 profile 分離、股票原修訂鐘及 registry 範圍；30 項相關回歸通過。三檔 targeted mypy 通過。此階段尚未完成實際 bounded 市場重建／新 fit，不能以程式或測試通過代替產物驗收。

上一批 `2722d411` 已合入 dev `8674cf14`。合入前 207 個其他 owner dirty 檔中，206 檔 bytes 一致；`tests/test_r012_recommendation_artifact_persistence.py` 在六秒檢查區間內由並行工作變動，不在本批修改路徑，未暫存或回復；index 空。

實際 bounded 官方市場資料已從 producer `1b226702` 建置：`E:/codex_model_repair_20260923/bounded_official_market_restatement_v3_run01/manifest.json`，file SHA `129401a72b2f81dd0ef92617eb81706bda8a99600eab19e249a927a0ee8bf985`，dataset identity `5fc2b34d85d4e7ff2db8563ca41a1b00225a47f214e3fc2cceb0897b787bff5c`，實際修訂鐘 `2026-09-23T08:38:35.903787+00:00`。原 22,093 列中保留 **17,285**，排除 **4,808**，實際排除原因均是新官方交易日下的股票價格路徑不完整；不是刪除原檔或補價。13 年分片及研究 loader 通過。市場值改變 150,201 slots；H5／H10／H20／H60 label payload 分別改變 16,067／16,098／16,173／16,336 組。

第一次實際 fit 在 trainer 原有 fold gate 被拒絕，尚未產生模型：排除缺價列後，fold-002 的有效決策日 purge 不足 60 日。新 consumer 僅收緊研究訓練截止日，從原 `2017-08-17` 前移至 `2016-11-01`，測試日期窗不變；沒有修改 frozen trainer 或降低 purge／embargo。實際重新呼叫原 `_validate_samples` 及 `_validate_folds` 全部通過。四 folds train/test 現為 **1,318/1,953、3,394/3,472、6,887/3,950、11,145/4,284**；較晚修訂鐘逐筆保留，這是研究評估，不是正式歷史 OOS。證據為 `bounded_official_v3_strict_preflight.json`，另新增缺價後 purge 的邊界測試，相關 18 tests、targeted mypy 通過。

Root 另用唯讀 verifier 逐列比較父資料與新分片：**846,965 個**非市場 feature payload、全部 row keys／targets／state 精確保留；**224,705 個**市場／品質特徵及 **69,140 組、553,120 個欄位**的四 horizon outcome 以原始股票／官方市場價格和獨立 Decimal 算式驗算一致，未呼叫 producer 特徵或 label 計算函式。所有 4,808 個排除 row 均能直接找到不完整股票路徑，17 個缺價日期及受影響列數保留在 `bounded_official_v3_independent_values.json`。來源與分片 hashes 前後一致，公司事件只沿用已核對的 label-exclusion reader，不把這項來源解析宣稱為第二套獨立解析器。

`1b226702` 合入 dev `c02148a5` 時，210 個並行工作 dirty 檔前後 bytes 完整一致、index 空。全量 H5 v3 producer 仍持續執行；本次 bounded gate 修正只改 consumer，不修改已封存 bounded 資料或正在運行的 H5 producer。

## bounded v3 完整 fit 與最新資料推論

原 trainer 的所有樣本／fold gate 通過後，`training_run02` 完成 **17,285 列、兩個算法、三個特徵組、四個 horizon、24 個 experts** 的完整訓練；沒有減少 fit rows。實際 seed=42、HGB max_iter=60、Ridge alpha=1，threadpool=2；不宣稱這些參數等同於歷史正式模型。資料分片及訓練程式 hashes 在前後核對一致。fit receipt SHA `f95e525bc9387a7a9929eac1b92089f872438262e77c251dc6b4264c108115c1`，模型 SHA `2a1223e06563098f08c8d57e85ec71c2c61399621987b3f09c9ac1d3b1081ae9`，audit SHA `b8e2d628325406cca3cc8120fcd212e5013f7be7ec85bedc04b446370f31ecb3`；根目錄為 `E:/codex_model_repair_20260923/bounded_official_market_restatement_v3_run01/training_run02`。

隨後從正式 SQLite 的新唯讀 transaction 擷取股票前綴，市場仍讀已核驗的官方來源。實際 captured_at=`2026-09-23T16:48:42.586694+08:00`、feature as-of=`2026-09-22`，包含 1256／1477 的 13 檔 × 24 experts 共 **312 組**當日研究預測成功。新輸入 dataset identity `321f672a4c7f5fefe5b21c9b719ff031e21bbb9229f45872c011329df67faf07`，manifest file SHA `696b289d9d0ed8b4f0b0a0fee4551276a47b9d4f7b3dd62335f9215270403f2a`；不是把訓練資料集身分假冒為當日輸入。

推論 receipt 位於 `E:/codex_model_repair_20260923/current_inference/bounded_official_v3_run01/bounded_current_heads/cb6fea7fad1dab2df9261ea640e32d41fadb6b841eafb986810765d332b5019f.json`，file SHA `9355d7683d6fd7bd081eca0b607f94d30a1c0fd0ddbccf8e45abcd913e4429c8`。production blend=0、allocation proposal=null、formal OOS／歷史 PIT／production action／promotion／broker order 均 false。312 組均無 neutral fallback，產業 excess head 全部維持 missing；不是用 0 代填。

獨立 verifier 已逐筆驗算 **327,816 筆 base OOF、13,659 個 unique test rows、96 個分組**，重新依各 fold 有效訓練列計算 train-only 基準，分片／audit hashes 前後不變。四期間 pooled MAE、downside Brier 均未勝基準；新舊 v2/v3 母體不同，不能以表面數值變化判定來源修復變好或變差。完整表、方法、證據 hashes 與限制見[bounded v3 評估](BOUNDED_RESTATED_RESEARCH_FIT_QA_2026_09_23.md)。

底層 `MLAllocationInferenceService` 的明確研究輸入分支也檢查官方市場契約，防止直接呼叫底層時略過 app wrapper 的來源限制。回歸驗證舊混合來源遭拒、另一批具有相同官方契約的新輸入可用；一般入口與 62 欄 ABI 不變。相關八項 tests 及 targeted mypy 通過。此 consumer guard 不改任何 dataset producer 或訓練數值。
