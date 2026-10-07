# 完整母體逐段核驗讀取 API

parent 新增 `read_verified`，沿原 strict read 核驗後回傳 package 與 immutable child batch tuple。原 `read` 保持 dict 行為，不累積 batch。取消回呼在入口與 child batch 前後檢查；單次 child exact 讀取仍需等返回後才檢查。

StoreReader 新增 `read_exact_with_verified_parent_callback`，完整 receipt graph/layout 核驗保持原路徑。只對所選 receipt prefix 逐段核對來源、方法、日期、分母、計數與 calculation identity；通過該段檢查後同步交付 callback，隨後釋放 context。每段最多 256 股票；VerifiedState 不保存全母體 snapshots。後段失敗或取消則 API 拋錯，呼叫端必須丟棄先前 callback 暫存，不能發布部分查詢結果。沒有 callback 與取消參數時沿舊 dict 路徑。

中央 parent 全檔 92376 terminal0：4 passed in 12.12s。中央 store callback／empty／excluded 兩案：2 passed、5 deselected in 3.84s（`C:/t/store-verified-central-20261007-a`）；這不是整份 store suite 通過聲明。owner 真 257 檔、兩段 parent 測例 2806 terminal0：1 passed in 296.20s，256+1 snapshots 與 pins／manifest SHA／舊 state parity 皆核對；另單段與空母體兩案 2 passed in 4.17s。各自型態、語法與 diff check 通過。

查詢層採用此 API 的改動另行驗證。此 API 完成不代表全母體查詢延遲達標；原非剖析 257 固定查詢 35.8078 秒仍是目前對照，尚缺 true 1000／完整市場與 cold/warm p95 的驗收。
