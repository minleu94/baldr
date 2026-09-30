# 8183 官方終止公告 inactive evidence 研究驗收（2026-10-01）

> 供 PIT taxonomy owner 合併至每日 preopen QA。本文記錄獨立 source/parser 驗收；不是 taxonomy bundle、正式 security classification 或正式接受紀錄。

## 結果

取得並保存 TPEx 官方公告的真實 HTTP 200 response bytes。請求在台北時間 2026-10-01 05:23:55.086807 完成，早於 2026-10-01 08:30 決策 cutoff；因此資料不是 cutoff 後補抓，也沒有回填更早日期。HTTP response 為 21,378 bytes，SHA-256 為 `sha256:735e9596680ca64cf5dc5d4b77e9784493da22375bf7e2911ffae750c0e01d47`。

原始檔與 HTTP metadata 以 create-only 方式保存在 ignored QA root：

- Raw：`output/qa/pit_8183_tpex_termination_diagnostic_20261001/attempt_20260930T212353756235Z_authorized_retry_7c96e318/announcement.html`
- Metadata：`output/qa/pit_8183_tpex_termination_diagnostic_20261001/attempt_20260930T212353756235Z_authorized_retry_7c96e318/metadata.json`
- 驗收輸出：`output/qa/pit_8183_termination_evidence_20261001/verification_20260930T142740028918_531a28/live_raw_no_write_parse.json`

直接來源為 [TPEx 8183 終止櫃檯買賣公告](https://www.tpex.org.tw/storage/eb_data/11509/11500054131.html)。保存的原始 HTML 顯示：發文日期為民國 115 年 9 月 3 日；公告對象是台灣精星科技股份有限公司、股票代號 8183、上櫃證券；自民國 115 年 9 月 23 日停止櫃檯買賣，並自民國 115 年 10 月 1 日終止櫃檯買賣。公告另明載每一股 8183 普通股換發 6191 普通股 0.342 股。這些事實均由保存的 HTML bytes 解析，不是以搜尋摘要代替原文。

HTTP `Content-Type` 沒有 charset 參數；保存的 HTML `<meta http-equiv="Content-Type">` 宣告 UTF-8。解析器記錄 `charset=utf-8`、`charset_source=html_meta`，並將解析出的公告／停買／終止日期與 source spec 交叉核對。實際原始 bytes 的驗收在記憶體中完成，只留下 QA 摘要；沒有寫 taxonomy bundle、canonical daily root、正式資料庫、pointer 或發布狀態。

## Classification 邊界

這份公告支持在 **2026-10-01 08:30 台北時間 cutoff** 將 8183 表示為獨立的 `proven_inactive_common_stock` research-only proof，`eligible=false`。它不提供 ISIN 或 CFI，不構成 active `OfficialSecurityRecord`，也不帶 `historical_pit`、`formal_credit` 或 formal OOS 資格。終止生效日以前的歷史型態仍需各自有效的歷史來源；不得用這份 10/1 終止公告追溯填補。

整合已完成：C-owned split producer 將當日 1,988 檔 company denominator 與 Rule 1,932 檔候選 universe 分開綁定，將 8183 proof 作為獨立 overlay；實際 2026-10-01 capture 的 attempt custody、v2 bundle/source/identity/sidecar 與 reader readback 均完成。這保留完整 denominator；不能因為 security source 缺件就刪除 8183，也不能把缺件一律轉成 inactive/excluded。其他 active 或 unknown security 仍走既有 exact market / ISIN / CFI fail-closed guard。整合後資料仍是 research-only split candidate，不能供 Formal consumer、歷史回填、OOS 或 credit 使用。本文的原始公告與 proof parser 驗收範圍不變；整合層測試路由、實際 capture/readback 的最終驗收由 PIT owner 的獨立 QA／receipt 保存。

## 實作與驗證

獨立解析器與型別位於 [pit_inactive_security_termination_evidence.py](../../data_module/pit_inactive_security_termination_evidence.py)，focused tests 位於 [test_pit_inactive_security_termination_evidence.py](../../tests/test_pit_inactive_security_termination_evidence.py)。公開 API 為 `parse_official_termination_notice(raw_html, response_metadata, spec, actual_capture_at, real_cutoff)`；`validate_official_termination_proof_readback(...)` 會用同一份 raw bytes 重算並拒絕欄位被改動的序列化 proof。

解析器只接受精確 HTTPS TPEx host 與 `/storage/eb_data/<ROC年月>/<notice-id>.html` 路徑、無 redirect 的 HTTP 200、與 raw body 相符的 bytes/hash、已宣告且無衝突的 charset、capture 時間不晚於 cutoff、公告日期不晚於實際擷取日，並驗證 issuer、symbol、market、三個日期及普通股轉換字樣。普通股轉換必須由標題中的「issuer + symbol + 以下簡稱 alias」先建立目標 issuer alias，再由同一對價句確認該 alias 每一股普通股換發普通股；其他公司即使同份公告也提到普通股轉換，不得替目標 issuer 補型態。Proof schema 明列 `isin_code=null`、`cfi_code=null`、`active_security_record=false`、`eligible=false`、`formal_credit=false`、`historical_pit=false`。

Fixture 是明確標示的合成 HTML；只重現真實 HTML 的日期標籤、主旨/代號/alias、事件日期、普通股對價句與 meta charset 結構，並非官方原文。另以保存的 21,378-byte 官方原文做獨立 no-write parse，包含 alias 對價主體綁定，結果可見於前述 QA JSON。Focused 測試覆蓋非 200、來源 URL/host/path、錯誤代號/market/date、缺少普通股證據、其他 issuer 普通股對價負控、raw hash/大小不符、擷取晚於 cutoff、公告日期晚於擷取日、終止尚未生效及 proof readback tampering。

驗證結果：

- `.\.venv\Scripts\python.exe -m pytest tests\test_pit_inactive_security_termination_evidence.py -q -o addopts= -p no:cacheprovider`：18 passed。
- `.\.venv\Scripts\python.exe -m py_compile data_module\pit_inactive_security_termination_evidence.py tests\test_pit_inactive_security_termination_evidence.py`：通過。
- `.\.venv\Scripts\python.exe -m mypy data_module\pit_inactive_security_termination_evidence.py`：`Success: no issues found in 1 source file`。
- 可核對最終 logs：`output/qa/pit_8183_termination_evidence_20261001/final_verification_20260930T143042619942_58db49/`。
