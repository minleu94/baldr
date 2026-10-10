# P08 前向現金開戶（2026-10-10，完整 P08／M3 未完成）

已正式加入策略版本專屬的前向空倉開戶 writer；沒有執行真帳戶開戶、daily producer、排程或交易。完整需求與待辦見[補完進度](BALDR_PRODUCT_COMPLETION_STATUS_20261010.md)。

## 契約與來源邊界

`StrategyPaperAccountCashSeedWriter.create_cash_seed()` 要求明示 strategy ID、exact version ID 與 account namespace。既有 `StrategyPaperAccountService.select_exact_version()` 必須回報 READY，並核對 binding 及其 pinned policy／cost model／benchmark artifacts；初始資金500000與最大持倉8再與既有 policy 核對，不以缺件預設值替代。成功只在該 namespaced personal state DB 保存 Decimal 現金500000、NAV500000、空持倉及 `paper-portfolio-snapshot-receipt.v2` 的 `account_cash_seed` 收據。

收據保存 binding hash、account namespace、空持倉 hash、canonical UTC aware 寫入時鐘。日期由該時鐘轉成台北自然日，早於 binding start date 即拒絕；呼叫端不能回填歷史時間。Seed 不讀價格、推薦訊號或 fill，不把現金開戶當作歷史 PIT、成本 basis、benchmark 或績效資格。

`append_account_cash_seed_once()` 在同一 `BEGIN IMMEDIATE` transaction 內核對帳戶尚無任何 snapshot，才寫入 snapshot／positions／receipt。一般 `append()` 收到 cash-seed kind 也委派此入口，不能繞過首次檢查；不同日期並發仍只有一筆成功。無 namespaced route、已有 snapshot、錯帳戶或非空持倉一律拒絕。原 v1 unknown／synthetic seed_reference 與舊 append 呼叫保持相容；非字串或未知 receipt schema 以 ValueError 拒絕。

## Root 審查與正式驗證

Root 審查原候選後要求補 transaction 內首次檢查、public append 不可繞過、flat store 拒絕及 malformed schema 負例。最終候選凍結於 `output/qa/p08_account_cash_seed_20261010/`，patch SHA `2a39f14f738b1ef2cc9a5d3840b730e93fadb0b22f641642892fcb81c8e10e4b`。Root 再核 formal preimage、所有 candidate postimage、七份 dependency pins、QA artifact SHA 與 apply-check；套用後三份正式來源與凍結 LF postimage 相符。

正式 import 測試：

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_strategy_paper_account_cash_seed.py tests/test_paper_portfolio_snapshot_receipt.py tests/test_strategy_paper_account_binding.py tests/test_paper_portfolio_daily_runner.py tests/test_paper_trade_ledger.py -q -rs -o addopts= -p no:cacheprovider --basetemp=.t/p08_cash_formal_root01
```

結果 **74 PASS／1 skip／4.59秒／native exit0**。Skip 是既有 Windows link/reparse setup 的 OSError，該分支未驗；不是通過。兩份來源 mypy、三檔 py_compile 與 diff check 通過。測試涵蓋 exact binding、政策 tamper、時區／未來起始日、同日不同策略分離、既有 snapshot、跨日期並發、flat store、JSON schema、持倉限制及 receipt insert 失敗全交易 rollback。只用 pytest 合成 JSON／SQLite，不讀 D 市場資料或真帳戶。

## 後續與回滾

Daily writer 仍需真正 current decision identity、同列多價欄的可得時鐘、prior snapshot、依實際執行次序保存的 fills、零成交 checkpoint、ledger 前後身分、跨 DB 復原、成本／benchmark 與週報資格。現有 weekly blocker 保持；正常 UI 尚未接開戶入口，不能把此後端切片算成完整策略帳本產品。

本次正式路徑為 `app_module/paper_portfolio_snapshot_repository.py`、`app_module/strategy_paper_account_cash_seed_writer.py` 與 `tests/test_strategy_paper_account_cash_seed.py`。原 repository raw bytes 保存在 ignored 的 `output/qa/p08_cash_seed_root_20261010/rollback/`。程式回滾只還原本任務差異、先核對他人後續修改；任何已存在帳戶 DB／snapshot／receipt 都保留，不以刪資料作回滾。
