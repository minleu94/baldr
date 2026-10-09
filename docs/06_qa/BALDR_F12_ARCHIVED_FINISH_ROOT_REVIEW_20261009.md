# F12 封存研究收尾中央複驗

獨立審查曾拒絕 archived finish 建立歷史 provider，因 constructor 會重新解析原 DB/raw 路徑。Root 對照審查時 SHA 與本次 preimage，確認來源增量只新增 `_RawArchiveVerificationRoots`、替換 archived finish 的 provider clone，以及擴充內部 verifier 型別；其他三個來源模組 SHA 維持原審查值。保存來源的 identity、bytes、安全邊界與 V1 live 驗證未在此修正中放寬。

Root 實際執行的新歷史路徑陷阱與晚到來源變動五例為 5 passed、17 deselected，1.08 秒；完整 exact reopen／P03 sources／snapshot lifecycle 為 58 passed、1 skipped，10.33 秒，程序 exit 0。日誌分別為 `output/qa/f12_archived_finish_no_historical_resolve_20261009_a/root_targeted_review_a.log` 與 `root_full_review_a.log`。唯一 skip 是此環境無法建立一般 file symlink，不能列為通過；真 directory junction 正反例仍有實際覆蓋。

此輪來源 SHA：`fundamental_read_snapshot.py` 為 `74BF6146B52D2F548EEBC8A71643299C87047CDF8BA5F7516BEDFFA7B571EFE1`；測試 SHA 為 `AB0F58C65A2CAF16B501EF5B537AA2F242B44F50F778F1BA686562312BACF355`。preimage manifest 與窄修正前原檔保存在同 QA 目錄的 `preimage_manifest.json`／`preimage/`，舊獨立審查結論保持原貌。

尚未接受最終 backend 增量：新 archived route 仍須補入口預取消與載入後 finish 取消，確認不發行完成結果、連線閉合及保存 snapshot/archive 不變。完成這兩例再核最終版本。此處所有證據是隔離合成來源，不代表正式資料、F12 全母體 query、Main/UI、收藏、EXE 或真人接受；原補完範圍保持。
