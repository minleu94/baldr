# 月營收年增率精確事實投影

P03 的 F12 第一葉片沿既有 CurrentMonthlyRevenueReadResult 與同報告上年比較基期，保存 current／comparator 的 TWD monthly_flow、原件 SHA、raw／derived source version、observed／official available／effective available 時間與可得性依據，再以 Decimal 計算 ratio 和 percent。兩種單位分欄，門檻由呼叫者明示，沒有新增預設推薦門檻。

缺基期、零或非正基期、來源／版本／市場／單位錯配、未知可得性或未來資料均留下具名 unknown；local_verified_observation 不能冒充官方公告時間。現在觀察的事實不取得歷史 PIT 或正式交易資格。排序以一趟分流 known／unknown，再穩定排序，未知值雙向置尾、同值按股票代碼升序，不以完整 known 清單逐列比對。

中央19項回歸通過，包含純結果與既有 Decimal 語義、同報告基期、時區／截止、未來 append 不改原結果、來源身份、單位、缺值及2,000筆排序的比較次數。中央 log 在本機排除檔 `output/qa/baldr_completion_m2_20261007/p03_yoy_root_20261007_a.log`。全域 mypy 885檔通過，但其中 source session 仍未取得提交資格。

本次只有精確事實／條件／排序核心。完整母體來源 session、immutable 保存／query／UI 與正常更新旅程仍待完成。來源 session 的合成試驗發現 SQLite mode=ro 可能在原 WAL 庫旁新增 sidecar，因此不能用 open 後的 pins 掩蓋原件副作用；後續需明示隔離 captured／reader copies，只在 reader 副本開 SQLite，保留原 main／WAL／SHM 起訖 bytes 核驗。此缺口不以純 F12 測試通過折抵。
