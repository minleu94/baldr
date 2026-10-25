# Gate 1 Advice 分類缺口修正 — 2026-10-24

## 結果

修正 `AdviceComposer` 的 Professional Mode 分類：只有來源策略明確標示 `promoted` 才能進正式 Advice；策略狀態缺失、空字串、未知或已退休等非 `promoted` 狀態，均列為 Professional 研究候選。策略政策原本拒絕新增建議的行為與 Advice DTO schema 未變。

這補上 Advice 層的分類安全缺口，不代表 Gate 1 整體通過。它沒有補出 Guided Mode 尚待 Owner 裁定的風險參數，也沒有提供正式來源、PIT、Portfolio current weights、自然 evidence 或 Owner UAT 證據。

## 驗證

- `py_compile`（Advice Composer 與聚焦測試檔）：**pass**；`tests/test_advice_composer.py`：**17 passed**。
- 最終驗證由受控 Windows Job 執行：啟動前可用 RAM 31,213,363,200 bytes；Job committed memory 上限 8 GiB、程序上限 12、kill-on-close 開啟；Job 成功附掛與關閉，退出碼 0，沒有強制回收。
- 新增案例覆蓋策略狀態為 `None`、空字串、`unknown`、`retired` 時仍分類為 Professional 候選，並確認明確 `promoted` 保留正式分類。
- `git diff --check`：通過；換行格式提醒屬既有 Git autocrlf 設定。

## 範圍與限制

- 沒有改 Advice action、分數、配置、來源資格、資料內容或交易行為。
- 手動文件補充 Professional 分類判讀；Feature Map 登記 Advice Composer 與聚焦測試。
- 本收據只證明上述分類契約與聚焦測試，不代表完整 Advice 端到端、正式資料 Gate 或投資有效性驗收。
