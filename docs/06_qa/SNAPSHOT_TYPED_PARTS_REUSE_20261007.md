# 技術來源快照單次解析重用

快照 validator 完整核驗原 mapping 後回傳私有 frozen typed parts。from_dict 沿用同批 rows、pins、sessions 與 rules；from_json 只在同次解析的 canonical bytes 回轉比對重用已核 session fingerprints。沒有跨操作快取；公開 API 與普通 to_dict／to_json 重建和重驗方式不變。

決策日／截止、來源 clock、raw row／window／session pins、計算契約、規則重新計算、浮點拒絕、JSON 大小與 canonical identity 檢查均保留。中央 snapshot 與 window reuse suites **37 passed in 4.74s**，四檔合併 mypy 通過。Agent 額外 repository／store 取消、篡改與歷史 prefix／CAS 回歸 **14 passed / 1 symlink 權限 skip**；snapshot suite 30 passed。各 attempt 原始 log 獨立保存，首輪兩個失敗屬測試型別正規化比較及 Windows cp1252 subprocess 輸入，後續修測通過。

同一原 257 股合成 pins 的非 profile 單次量測 **5.282 秒**，query identity、來源 pins、counts 和前五列皆相同；前一 window reuse 量測為 4.824 秒。這次量測與候選建置同時進行，沒有證明延遲改善，不能宣稱 p95 或真實全市場效能達標。可證明的改善是每次 decode 只解析各 typed part 一次、每個 session fingerprint 只核一次；仍需完整效能 gate。

中央原始紀錄在 `output/qa/baldr_completion_m2_20261007/snapshot_parser_root_20261007_a.log` 與 `full_v4_query_parser_reuse_measurement_20261007_a.json`。原 failed attempt 和舊量測未覆寫。
