# 官方當下處置來源葉片與截止時間核驗

F17 新增 CurrentOfficialDisposalReader，從既有 current-market-status pointer 取得固定 snapshot／manifest／原始回應 pins，或以原 source pin 精確重開。每件有 bytes 上限、SHA 與路徑身份守衛；重開不讀 latest pointer。TWSE 沿既有官方 parser；TPEx 沿已保存官方 Swagger 與真 endpoint 回應的六個字串欄位，不以網站表格中文欄名猜 JSON schema。

TPEx schema 原證據是 2026-09-30 22:38:52.420371 UTC 完成的 Swagger，SHA256 05af7755d0d528626c104f7a8ccd7b00c6a0cf228d30bcb4669020e514eb0c7e；endpoint 原回應觀察於 2026-10-04 00:21:39.057312 UTC，29 列、27,979 bytes、SHA256 25a0905e95b86046493320725927d9a2f32fa5e7c5657162363282acc36340b5。這是既存官方原件唯讀驗證，不是 10/7 新擷取或今日 coverage 證明。公開提交只有 parser／合成測試，不含原回應或私人來源。

公告日、處置起迄日、原觀察時間與來源 dates 分開保存。官方 available_at 未知，不回填公告日或觀察日；資料保持 current_only、historical_pit_eligible false。缺列、空回應、錯市場、schema 不符及部分壞列不當作「沒有處置」安全證書。有效正面事件可顯示，但保留來源部分缺件；不計預警或放寬 S46 T+1。

未來函數自查發現原相對時間守衛不足以拒絕自洽的整組未來來源。兩公開入口現各取一次 UTC read_now；明示 cutoff 必須 aware 且不晚於 read_now，pointer publication／snapshot observation／每件有時間的 capture 均不得晚於同一 cutoff。公告晚於觀察仍拒絕；未來生效期可以是已公告的事件。cutoff 不改 source pin 身份，不提升歷史資格。

中央完整來源＋截止時間測試 29 passed（1.27 秒），包含上述原 TPEx 29/29 列精確重讀；隔離根 C:/t/f17-cutoff-root-20261007-d，收據 output/qa/f17_cutoff_root_20261007_d/exact_capture_receipt.json。未給明示原件 env 的一般測試是 28 passed／1 skipped，不混成真原件核驗。首輪 28/1 相對時間 fixture 失敗已保留並改為歷史時點，獨立測舊守衛。中央 typing 發現測試的 optional env 未收窄，補非空斷言；不更改產品核驗或來源。

此葉片尚未接完整母體保存／可選條件／正常 UI 更新與收藏旅程。既有 refresh_current_market_status_observation.py 已具 capture／pointer 更新工具，沒有新增 harvester，也未執行正式更新。這是 P03/F17 的來源基礎，不是 P03 或 M2/M3 完成。回滾僅撤回兩個新檔及本包文件，不改原保存來源或既有 updater。
