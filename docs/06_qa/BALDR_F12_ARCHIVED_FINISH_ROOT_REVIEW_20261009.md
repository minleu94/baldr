# F12 封存研究收尾中央複驗

獨立審查曾拒絕 archived finish 建立歷史 provider，因 constructor 會重新解析原 DB/raw 路徑。Root 對照審查時 SHA 與本次 preimage，確認來源增量只新增 `_RawArchiveVerificationRoots`、替換 archived finish 的 provider clone，以及擴充內部 verifier 型別；其他三個來源模組 SHA 維持原審查值。保存來源的 identity、bytes、安全邊界與 V1 live 驗證未在此修正中放寬。

Root 實際執行的新歷史路徑陷阱與晚到來源變動五例為 5 passed、17 deselected，1.08 秒；完整 exact reopen／P03 sources／snapshot lifecycle 為 58 passed、1 skipped，10.33 秒，程序 exit 0。日誌分別為 `output/qa/f12_archived_finish_no_historical_resolve_20261009_a/root_targeted_review_a.log` 與 `root_full_review_a.log`。唯一 skip 是此環境無法建立一般 file symlink，不能列為通過；真 directory junction 正反例仍有實際覆蓋。

此輪來源 SHA：`fundamental_read_snapshot.py` 為 `74BF6146B52D2F548EEBC8A71643299C87047CDF8BA5F7516BEDFFA7B571EFE1`；測試 SHA 為 `AB0F58C65A2CAF16B501EF5B537AA2F242B44F50F778F1BA686562312BACF355`。preimage manifest 與窄修正前原檔保存在同 QA 目錄的 `preimage_manifest.json`／`preimage/`，舊獨立審查結論保持原貌。

取消補測已完成。Root 實際執行三個新案例為 3 passed、22 deselected，0.93 秒（`root_cancel_review_a.log`）：入口預取消不建立 operation／SQLite；已完成 snapshot 的 revenue wrapper 在投影後取消不發行 revenue cohort；底層 archived finish 在最後 archive 驗證後取消，不發行 snapshot 或 revenue reference。三例核對 reader 閉合及保存來源 inventory 不變。Owner 的同版完整回歸為 61 passed、1 skipped，12.05 秒，Root 已讀終態日誌。最終測試 SHA 為 `CA2570F58071F4E582E15C35868AED5E13F5433215DF2FAFF29714961BC7C3D2`；四來源 SHA 維持已審查值，Root 五檔 py_compile 通過。

中央接受本次 archived-source backend 增量，原獨立審查 blocker 已以窄修正和明確 instrumentation 補齊。所有證據是隔離合成來源，不代表正式資料、F12 全母體 query、Main/UI、收藏、EXE 或真人接受；後續索引／複合查詢相容性與產品接線另行驗證，原補完範圍保持。

來源與測試已保存至 dev 提交 `f6dd33b3`。Root 另實際執行 YoY index 與 revenue query 兩檔為 9 passed、139.10 秒，程序 exit 0，日誌 `root_index_query_a.log`。這證明該索引／query 的現有合成契約相容性，不證明全母體 UI 或效能達標；尚未測各階段耗時，不能將整組時間當成個股下鑽時間。現有三組條件是技術／官方處置／營收 YoY，不能解讀為已提供 MoM／連續成長。
