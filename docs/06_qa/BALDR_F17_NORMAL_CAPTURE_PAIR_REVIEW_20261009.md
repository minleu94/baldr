# F17 正常 capture 至雙 reader 接點核驗

Root 在全新隔離合成目錄實際執行 `scripts.refresh_current_market_status_observation.capture_sources`，包含三組市場名錄與兩組官方處置 source spec。Fetcher 只回傳合成 bytes，沒有網路、SQLite 或正式資料操作。

正常 updater 保存的同一 pointer 可由 `CurrentMarketAssignmentReader.from_pointer` 與 `CurrentOfficialDisposalReader.from_pointer` 接受；兩組 typed pins 的 output root、run ID、pointer／snapshot／manifest SHA 精確相同。第二次 capture 推進 mutable pointer 後，兩組 `from_exact` 仍重開第一版；pins 與 1101 觀測值一致，第一版所有保存檔 bytes SHA 保持不變。

收據為 `output/qa/f17_capture_pair_es46_o1d/receipt.json`，腳本為 `output/qa/f17_normal_capture_pair_20261009_a/root_capture_pair_probe.py`，成功日誌為 `native_probe_attempt02.log`，terminal exit 0。探針使用既有測試的合成名錄／source spec helper；官方處置 raw 為空陣列，不是實際事件或 no-risk 證明。

第一次 sandbox 讀取因 Windows strict resolve 的 WinError 5 停止。第一次 native 執行則因探針錯把 dataclass observation 視為有 `to_dict` 方法而失敗，保存於 `native_probe.log`；修正為 DTO 相等比較後在新合成目錄成功。未修改產品讀取器、updater 或來源保護。

此結果證明正常 capture 與既有雙 typed reader 的資料形狀可以銜接。尚未執行 bundle producer、UI、catalog、收藏或跨程序完整旅程；不能提升 current-only／PIT 資格。接續 adapter 應凍結同一版兩組 pins，拒絕兩次讀 pointer 之間被更新造成的混版，再把明示 pins 與同 cutoff 的完整技術 receipt 交給 `create_from_pins`，不在下游改讀 latest。

## 受控接線與回滾範圍

預定新增 `app_module/selection_current_source_pair.py` 與專屬測試：提供明示 aware cutoff 的同版雙來源入口與既有 bundle writer 呼叫 adapter，不修改固定 bundle writer、兩組來源 reader、updater 或任何 agent 的實作。兩組 reader 必須有完全一致的 run／pointer／snapshot／manifest 與原觀察時刻；混版或取消在 writer 呼叫前拒絕。Look-ahead 自查：cutoff 由 caller 明示，既有 reader 拒絕其後發布／觀察資料，下游既有 writer再核技術來源 cutoff；不以目前時間補歷史資格或公告時間。

回滾方式：確認後續 caller 與未提交變更後，撤回此新增 adapter 與其專屬測試的提交；不刪保存 capture、原件或 QA。此入口尚未接 UI，不影響已固定 s3 或 F02 writer SHA。實際完整 producer／UI 接線接受仍須另取得證據。

接線已實作，定向測試 terminal exit 0、8 passed／0.51 秒，日誌 `output/qa/f17_normal_capture_pair_20261009_a/adapter_tests_c.log`。真正合成 capture 驗同版讀取／舊版 exact reopen、讀取中 pointer 前進拒絕、決策後發布拒絕、取消與非 bool 回呼拒絕；writer delegation 使用 mock，只證明參數轉交及取消時不呼叫，不能冒稱完整產製接受。Targeted mypy 1 檔通過，兩個新增檔 py_compile 通過。

初輪 4 passed／2 failed 保留：測試錯把 market source pin 視為含 PIT 欄位，以及用未來 cutoff 模擬 race 被既有來源 guard 正確拒絕。修正為觀測 DTO 的 PIT 欄位、兩個已生成 capture 的 mutable pointer 競爭；未改產品 guard。第二輪 6 項通過後再補決策後來源與完成讀回後取消兩項。UI 與正常按鈕 caller 仍未接入。
