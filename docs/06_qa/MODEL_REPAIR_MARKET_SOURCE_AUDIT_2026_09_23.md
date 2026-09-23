# 模型完整重訓後的大盤來源差異（2026-09-23）

## 判定與範圍

H5 v2 完整 fit 已完成，但市場特徵組的 heldout 風險預測大量偏高。獨立核對發現 `market_indices.成交量` 混用兩種來源，且 TWSE FMTQIK 分支以收盤指數代填開／高／低。這是資料語意問題；目前證據不能把 Yahoo 的 Volume 一律乘上 1,000，也不能把指數後期的正常漲幅判為錯價。

本次來源查核只讀取 run02 快照與官方月報，沒有修改正式 SQLite、封存模型或 v2 資料。這項額外問題尚未修好，因此模型保持研究狀態；不能宣稱「完整修復已驗收」。

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
