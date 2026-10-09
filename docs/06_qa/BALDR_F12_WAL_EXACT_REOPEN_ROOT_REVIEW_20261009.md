# F12 未 checkpoint WAL 精確重開審查

Root 已直接閱讀 `test_daily_market_monthly_revenue_exact_reopen_v1.py` 的 WAL 案例，以及 `output/qa/F12_MONTHLY_REVENUE_EXACT_REOPEN_WAL_20261009_A/` 的 attempt05 terminal、child receipt、source inventory。沒有重跑或改寫 owner 封套。

## 證據與裁決

- 實際 terminal exit 0，1 passed／5 deselected，1.29 秒。
- writer 在 WAL 模式下保持開啟並停用 autocheckpoint；新增 probe 表與 `9999` 記錄後，main DB SHA 仍不變，WAL／SHM 確實存在。
- fresh child PID 49864，launcher PID 44632；child 從新 operation private reader 查到該 WAL 記錄。兩次觀察到的 SQLite open 都指向這份 private reader，沒有開原 DB 或 saved reader。
- Root 重新比較收據中的完整 pre/post inventories：原 DB／sidecars、saved snapshot 與 raw HTML／CSV 各自完全相同，三組比較均 true；main SHA 前後亦相同。
- 測試比較完整 facts／fact identity ledger、三種 captured file role 與各自 SHA；原 source_scope 仍為 current_observed_only、availability unknown，historical／formal PIT 均 false。

此證據支持合成未 checkpoint WAL 保存來源的跨程序精確重開及原件保護，補足先前僅 rollback-journal 的範圍。

## 尚未完成

此 v1 重開仍檢查 live original DB 與 live raw capture 是否符合舊 pins；不證明 live 資料更新或缺檔後仍可重開。新 durable raw archive schema／入口由營收 owner 另行實作、測試並交 Root 審查，不得把本次 WAL 成功當作該功能完成。

UI、收藏、EXE 同版與真人可讀性均不在此案例範圍。原始資料及正式排程未納入測試。
