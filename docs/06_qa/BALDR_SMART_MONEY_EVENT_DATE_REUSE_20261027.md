# Smart Money 事件日期索引重用

## 範圍

Smart Money 批次語意摘要在確認交易日期索引升冪、事件列為有效 ISO 日期、每檔事件依原來源順序不遞增且不超過決策日時，直接重用日期映射與逐檔事件順序，省下每檔重解析及排序。任何日期型別、格式、日期集合或順序無法確認時，維持原本解析／排序路徑。沒有改來源資格、摘要規則、交易日窗或 Gate。

## 驗證與合成 A/B

- `tests/test_broker_flow_dashboard_query_service.py`、`tests/test_broker_flow_sqlite_read_repository.py`、`tests/test_smart_money_semantic_service.py`：57 passed；包含已驗證事件捷徑與異常順序／日期格式安全回退。受控收據：`output/tasks/smart-money-event-date-reuse-20261027/evidence/single_owned_qa_a20634ac55e54b50ac6f2ba06ced3f1e/receipt.json`。
- Scoped `document_control check --task` 對 Feature Map、QA 索引及本報告通過，沒有缺少的連結或錨點；收據：`output/tasks/smart-money-event-date-reuse-20261027/evidence/single_owned_qa_9e0ee6c6954b40b6adc067159f7ef131/receipt.json`。
- 合成 A/B 以 80 檔、60 個日期、每股票／日期 3 個分點、共 14,400 事件比較原始逐檔解析排序與日期索引重用；兩路徑輸出 digest 同為 `390c4ee11c4276959086f54222771bd7371447758c39f1e2c64c637f20e9195b`。交替執行 60 個樣本／路徑、各 2 次暖機，隔離計時停用循環 GC。

| 路徑 | p50 | p95 |
|---|---:|---:|
| 原逐檔日期解析／排序 | 10.044 ms | 11.263 ms |
| 已驗證日期索引重用 | 7.925 ms | 10.078 ms |

受控基準收據：`output/tasks/smart-money-event-date-reuse-20261027/evidence/single_owned_qa_eb7092413fdd49c4973b31926d747b10/receipt.json`。

## 限制

這是預載合成事件的語意整理微基準，不含 SQLite 查詢、價格載入、TaskWorker 排程或整頁呈現；測量結果不能外推成正式資料或 UI 端到端延遲。基準是在 Windows、Python 3.11.9、循環 GC 停用時採樣。必要 UI／Update 回歸、targeted mypy、編譯可查 `output/tasks/stock-research-name-search-20261027/evidence/required_ui_qa_results.json`；repo-wide mypy 同樣被未修改 T164 bridge 第 411 行語法錯誤阻擋。
