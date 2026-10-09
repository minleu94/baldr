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

## UI 接入前的時序限制

Root 已讀回既有 bundle writer `_open_pinned_sources`：市場 pin 的 cutoff 必須與技術 plan 的 `source_clock.decision_cutoff` 是同一 aware 時刻；兩個 exact reader 再以該時刻核原 capture。因此 UI 不能把剛更新的 current capture 任意接到早於該 capture 的舊技術版本，也不能將 cutoff 改為現在來繞過技術 plan。正常入口需選同一決策時刻的來源組；沒有相容保存來源時，顯示缺件並走新的完整來源準備／技術產製流程，不回填舊版。此限制尚須在完整 normal producer／UI 旅程驗證。

## 真正 writer 接線驗證

Root 重用 attempt03 已保存的合成技術母體（257 included＋1 excluded），以原五組已核 raw bytes 在新的 QA capture root 呼叫正常 updater，再經 adapter 呼叫未修改的真 `create_from_pins` 與 `read_exact`。terminal exit 0，258 列精確股票清單與原母體相同；原合成來源整棵樹與新 capture 的逐檔 SHA 起訖一致。收據 `output/qa/f17pairpub_5ktl4ism/receipt.json`，腳本 `output/qa/f17_normal_capture_pair_20261009_a/root_real_writer_probe.py`，日誌 `real_writer_probe_f.log`。此案例使用明示 frozen capture clock，不代表新即時官方更新、UI、不同程序或全市場接受。

真接線抓到零微秒表示的實際相容問題：市場 reader 用 `.000000+00:00`、處置 reader 用 `+00:00`，原 pointer／snapshot SHA 相同卻被 adapter 誤拒絕。現改為原來源與版本 SHA 仍完全相同，兩個時間欄位則核 aware instant；沒有改 cutoff、reader 或 writer 的 gate。新增零微秒真 capture 案例後 9 passed／0.64 秒，日誌 `adapter_tests_d.log`；targeted mypy 與 compile 通過。

前置探針失敗日誌 a–e 保留：完整 QA tree 深層 Windows 路徑、帶 `sha256:` 前綴的 raw pin 比較、上述時間誤拒絕，以及成功產製後 QA 收據錯用不存在的 `reference.to_dict()`。修正最後項為 dataclass `asdict`，在新獨立目錄重跑成功；未把只到產製或只到重開的部分結果冒稱完整 terminal 收據。
# 完整技術產製結果接續 gate

## 產製前固定來源的轉交

完整產製入口新增 `source_pair` 模式：caller 可在產製前成對核定官方來源，產製後使用原 pins，不再讀 mutable pointer。`pointer_path` 舊用法保留，兩種模式必須且只能指定一種；固定來源 cutoff 必須與技術 plan 相同。pair 直接建構亦核 reader 型別、版本、clock 與 aware cutoff，不允 caller 組合兩份來源。下游 writer 照常 exact 核原件，不以此 adapter 授予來源資格。

回歸 14 passed，2.82 秒；日誌 `output/qa/f17_normal_capture_pair_20261009_a/fixed_pair_handoff_b.log`。真單股產製結果案例中，新 pointer 的發布時間已在原 cutoff 後且重新讀取會被拒絕；固定原 pair 仍轉交原 pins。混版 pair、改 cutoff 與同時提供兩種來源均拒絕且不新增 writer 呼叫。這仍是 backend 轉交驗證，不宣稱 UI 或完整 writer 新流程已接受。

新增 `publish_completed_technical_selection_bundle()`，只接收真正 typed 技術產製結果；整體與 receipt 都必須 complete，plan／receipt 缺件、取消或失敗均在來源 I/O 與 writer 呼叫前拒絕。來源 cutoff 沿原 plan，保存 pins 由產製結果取出，下游既有 writer 仍須 exact read 驗證 store。

合成回歸 13 passed（1.90 秒），日誌 `output/qa/f17_normal_capture_pair_20261009_a/complete_result_gate_b.log`。新增案例以真正單股技術產製器取得完整結果，驗證原 cutoff／plan／receipt pins 轉交；另外三種不完整結果均不發布。首次 sandbox 因 WinError 5 路徑 resolve 失敗，原測試目錄保留，改以全新 native 隔離目錄測試通過。

此增量仍是 backend 轉交邊界，尚未串接 UI，新增單股案例沒有再次驗證完整 bundle writer 或 EXE；先前真正 writer 證據與本次證據範圍分開。

## 固定來源經真正 writer 保存與重開

新增獨立探針 `output/qa/f17_normal_capture_pair_20261009_a/root_fixed_pair_real_writer_probe.py`：exact 核讀原已保存的合成完整技術 plan／receipt，再固定成對來源；正常 updater 發布原 cutoff 後的新 pointer，重新讀 pointer 確實拒絕，但固定 pair 經未修改的真 writer 保存後，真 reader exact 重開成功。258 列股票順序與原件一致；原合成來源逐檔 SHA 與第二次 capture 後的來源逐檔 SHA 在 writer 起訖均一致。

原生 terminal exit 0，收據 `output/qa/f17fixedpub_mg48geel/receipt.json`，日誌 `fixed_pair_real_writer_b.log`。首次 sandbox 路徑解析 WinError 5 日誌 a 保留。這是同程序 backend 合成案例，使用明示 frozen capture clock，重用已保存的 producer 輸出，沒有新執行 producer、網路擷取或原始行情 SQL；不宣稱逐欄新舊技術值比較、UI、跨程序或 EXE 驗收。來源 coverage 仍為 partial，未升格為 complete。

另以獨立唯讀探針 `root_fixed_pair_readback_comparison.py` 比較新舊 258 列的 schema、股票、cohort role、排除原因、技術處理狀態與缺件標記，全部相同；完整 `technical_store` 保存 pins 相同，兩棵來源樹逐檔 SHA 起訖不變。terminal exit 0，收據 `fixed_pair_comparison_receipt.json`，日誌 `fixed_pair_comparison_a.log`。此比較覆蓋 bundle 保存的技術 projection 與指向來源，不是底層指標逐值比較。
