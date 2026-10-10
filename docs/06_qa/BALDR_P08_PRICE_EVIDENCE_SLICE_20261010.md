# P08 行情證據讀取切片（2026-10-10）

本切片屬於產品補完 P08／M3 的來源基礎；策略 seed、daily writer、成交帳本、benchmark 與績效資格仍未完成。狀態與全範圍見[補完進度](BALDR_PRODUCT_COMPLETION_STATUS_20261010.md)。

## 問題與修正契約

原 `data_module.twse_daily_price_publication` reader 選出一筆行情後，仍用 manifest 迴圈最後一份來源核對 raw／custody／observation／CSV hash。多份來源時，第一份的合法列會被誤拒；另外，發布列的 first-observed 時鐘未與來源回執核對。

Root 先以原正式路徑執行 18 項回歸（18 PASS／1.48 秒／native exit0），再使用假 HTTP 回應經實際 collector、同步與 publisher 建立私人合成資料。另存一份有效重封、僅把列 first-observed 改為 2000 年的負例，原 reader 仍回 `attested`。這證明時間一致性缺口；沒有修改正式市場資料。探針與收據保存於本機 `output/qa/p08_clock_root_review_20261010/`。

候選修正使用所選列的 `projected_manifest`，要求列 first-observed 等於該來源 first-observed；來源 first-observed／observed 分別等於 custody／observation receipt 的 captured-at，且 observed 不早於 first-observed。Publisher 與 reader 都要求 written-at 不早於 observed。Aware timestamp 先正規化為 UTC，不以交易日期推造可得時間。

舊 `read_sqlite_daily_price_evidence()` 參數及三欄 `DailyPriceEvidenceReadResult` 維持相容。新增 `read_sqlite_daily_price_scalar_evidence()` 在同一 SQLite snapshot 讀取指定欄位與列 hash，以 `mode=ro`、`PRAGMA query_only=ON`、`BEGIN`、`ROLLBACK`、close 完成；不另讀價格。無效或未列入 projection 的欄名、來源漂移及時間不一致回 `unknown`。

Scalar 是資料庫輸入邊界的原值；金融 caller 仍須驗證型別、用 `Decimal` 轉換，並核對 first-observed 與 written-at 均不晚於 decision clock。`attested` 不表示歷史 PIT、可交易價格、已扣成本或策略績效合格；NULL 也不能當有效價格。

## 驗證與整合狀態

候選封套 `output/qa/p08_price_reader_multimanifest_20261010/` 已凍結。Patch SHA-256：`4a16fa115c70c8c19714e0ff7ddb151a29cdef6f471b1616074c0ac5f24f1797`；正式 preimage SHA：`7aca1b09a19d0d5d5ac2d0cc5d4af1632c7c7e80e8d61bed2035e1dac73c412d`；postimage SHA：`b741f7fa1c3433483760c3bdd89b8bd7a8736da3ba3982022b7b19b8bf9f4e53`。

候選 overlay 取得 39 PASS（21 項新案例＋18 項既有回歸）、3.34 秒、native exit0。涵蓋實際合成 collector→publisher 的兩 manifest 成功路徑、首末列跨來源替換、有效重封的時鐘回填、等價時區、寫入早於觀測、無效 scalar 欄名，以及唯讀交易與拒寫。Root 全讀差異及耐久測試後已整合正式來源；正式 import 回歸取得 **39 PASS／2.86 秒／native exit0**，單檔 mypy、兩檔語法與 diff whitespace 檢查通過。正式檔經 LF 正規化後與凍結 postimage／portable test SHA 相同；Git 套用後的 CRLF raw hash不同不表示內容漂移。Windows reparse 專項未驗，不以此回歸宣稱整體 P08 完成。

正式驗證命令：`.\.venv\Scripts\python.exe -B -m pytest tests/test_twse_daily_price_multimanifest_reader.py tests/test_twse_daily_price_sqlite_publication.py -q -o addopts= -p no:cacheprovider --basetemp=.t/p08_price_formal_root01`。全部資料均在全新合成測試根；既有 create-only custody 使用核准的隔離執行權限，不連外或啟動正式產製。

回滾只涉及本切片正式來源差異及新增耐久測試；不重建或回填行情，不改排程、帳本或模型。原 probe、候選與失敗證據保留，不以還原覆寫其他 agent 的工作。
