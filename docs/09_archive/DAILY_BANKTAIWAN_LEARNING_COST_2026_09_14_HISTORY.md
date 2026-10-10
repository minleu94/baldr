# 每日推薦學習：臺銀成本估算 lane QA 紀錄

> **歷史狀態快照（2026-10-10）：** 本文的成本 lane、legacy fixed 50bp、active pointer 與接線敘述只反映 2026-09-14 當日的研究／合成範圍，不代表目前成本政策、排程、champion 或正式下單能力。同日另有 [獨立 05:50 BankTaiwan 營運 QA](DAILY_BANKTAIWAN_OPERATIONAL_2026_09_14_HISTORY.md)，兩者 scope 應分開讀；該次註冊／run 也不是目前狀態。現況看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) 與 [QA 導覽](../06_qa/README.md)，操作以 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md) 為準。

日期：2026-09-14
範圍：`banktaiwan-electronic-estimate` 研究用成本情境、每日 bounded replay、capture → natural outcome → promotion authority → consumer，以及既有 `legacy-fixed-round-trip-bp` 相容性。

## 驗收結論

- 臺銀電子下單成本使用 versioned policy 與明確 `policy_estimate_date`。市場 replay date 與 policy estimate date 分開保存並執行 look-ahead 檢查。
- `fees_tax_only` label 只使用可由價格與數量重算的手續費及賣出交易稅；滑價／成交流動性只保留為 diagnostic。缺少流動性觀測時維持 unavailable，不補零，也不阻擋這個研究 label。
- 成本、數量、lot type、instrument type 或 policy date 改變會改變 scenario hash，因此形成不同 experiment scope；跨日 replay 在同一 scenario cohort 內仍可聚合。
- 新 lane 一律為 shadow／research-only，`formal_order_allowed=false`；consumer projection 不會把估算成本變成正式下單成本。
- 同一 output root 若已存在另一成本 scenario 的 active pointer、challenger、latest status 或 decision receipt，CLI 會 fail closed 並回傳 `cost_scenario_root_conflict`，要求使用不同的 `--output-root`，避免覆寫 legacy state。
- 既有 legacy candidate、capture 可在隔離複本上完成驗證、frozen reuse、consumer reload；原始檔案 bytes 維持不變，舊 sample payload/hash 形狀維持相容。

## 精確成本抽查

以 2026-01-01 policy、1,000 股、買入價 100、賣出價 100.40 為例：

- 買進手續費：49 TWD
- 賣出手續費：49 TWD；賣出交易稅：301 TWD
- round-trip cost：399 TWD
- net profit：1.00 TWD；`net_profit_label=1`

此數值由 Decimal／整數分位計算；odd-lot 與整股最低手續費規則另有測試覆蓋。

## 自動化驗證

新增 `tests/test_daily_banktaiwan_learning_cost.py`，覆蓋：

1. versioned 臺銀 policy、精確 net、缺少流動性不補零。
2. 三個實際 market decision dates 在同一 evidence cohort 聚合。
3. sizing／policy date 改變 experiment scope。
4. 三個隔離合成 SQLite fixture market decision dates 的 capture → outcome 聚合；驗證 scenario、policy date、成本 label 與 liquidity 欄位一致。這不是自然市場實證。
5. authority adoption、consumer reload，以及兩種 tamper rejection：修改 net 後的 hash 不一致，以及把 buy/sell cost 改為 0、同步修改 net／label／sample fingerprint／receipt body hash 的 self-consistent undercharge；後者仍被 versioned policy 重算拒絕。
6. 合法 cost-unavailable（研究金額不足一整張）維持 after-cost unknown，且 price-only gate 不因缺少成本 label 而被誤判。
7. 現有 legacy candidate/capture 的 read-only frozen reuse 與 consumer 相容性。
8. bounded daily CLI 實際執行新 lane，以及共用 root 防覆寫與獨立 root 成功路徑。

主要執行命令：

```text
.venv\Scripts\python.exe -m pytest tests\test_daily_banktaiwan_learning_cost.py -q -o addopts=
```

提交前回歸結果：上述新驗收測試與相關 calibration／evidence／CLI／daily-loop suite 合計 `86 passed`；本次 11 個目標檔案的 mypy `Success: no issues found`，本次檔案 `py_compile` 通過。本線曾在 foreign dirty `app_module/industry_strength_service.py` 尚未修正時取得全域 mypy 4 errors；後續由另一條線修正後，父任務核對全域 mypy exit `0`、`608 source files` pass。該 foreign 檔案未納入本次提交。

## Real-data bounded smoke

以下 smoke 使用本機正式 SQLite source，output root 為隔離 temporary 目錄，沒有啟用 live capture，也沒有將 historical replay 當成 natural evidence：

```text
.venv\Scripts\python.exe scripts\scheduled\run_daily_recommendation_learning.py --data-root D:\Min\Python\Project\FA_Data --output-root C:\Users\archi\AppData\Local\Temp\codex-banktaiwan-real-smoke-20260914-c --source-db D:\Min\Python\Project\FA_Data\sqlite\twstock.db --symbols 1101,2330 --decision-date 2026-09-14 --history-start-date 2014-01-01 --replay-start-date 2026-01-01 --replay-end-date 2026-09-14 --training-as-of 2026-09-14 --max-decision-dates 100 --cost-scenario banktaiwan_estimated_research --research-order-quantity-shares 1000 --skip-capture-current
```

結果：process exit `0`；real source replay 產生 160 samples、160 estimated fee/tax rows，candidate artifact 寫入隔離 output root，`cost_scenario_hash=sha256:73ad38fa8a5cd983535f50fcaf99e168aea44400ac2e7428d58400a21f55e450`，`formal_order_allowed=false`。本次 decision 為 `retain_current`／`natural_forward_evidence_receipt_missing`，因為 smoke 沒有偽造 live forward capture；不是訓練或成本計算失敗。

source DB 前後 stat：size `3,568,181,248` bytes、LastWriteTime `2026-09-14T05:45:06.8888799-07:00` 均未變；replay receipt 標示 `SQLite mode=ro with PRAGMA query_only=ON`。這是 real-source read-only smoke，不代表正式 promotion eligibility。

## 目前排程狀態與下一步接線

目前正式每日排程仍使用 `legacy_fixed_bp` 的 fixed 50bp default；本次沒有把臺銀 lane 接入每日自動累積，也沒有把它宣稱成已完成的自然 forward learning。新 lane 目前只由受控 CLI／fixture 驗收與上述 real-source smoke 使用。

下一個明確接線點是 `scripts/scheduled/run_daily_recommendation_learning_pipeline.py` 將既有 `learning_arguments` 傳給 `run_daily_recommendation_learning.py` 的區段（cost flags 已可轉送）。接線時必須以獨立 root 執行，例如：

```text
.venv\Scripts\python.exe scripts\scheduled\run_daily_recommendation_learning_pipeline.py --data-root D:\Min\Python\Project\FA_Data --output-root D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan --source-db D:\Min\Python\Project\FA_Data\sqlite\twstock.db --cost-scenario banktaiwan_estimated_research --research-order-quantity-shares 1000 --max-decision-dates 100
```

`D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan` 僅為隔離研究 root 範例；不可與 legacy 50bp 的 shared root 混用。若要讓它成為每日正式排程，仍需另外確認 schedule ownership、source-contract readiness、自然 capture 累積與 promotion gate，並由後續接線任務明確核准。

## 安全邊界

- 不修改正式資料檔；測試使用隔離 SQLite fixture 或既有 artifact 的 temporary copy。
- 不允許以臺銀估算 lane 直接下單；研究成本不宣稱為實際成交成本。
- 既有 legacy fixed-50bp daily learning state 不在新 lane 中重訓、改寫或隱式轉換。
