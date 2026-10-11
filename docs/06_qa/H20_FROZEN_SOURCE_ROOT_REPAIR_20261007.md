# H20 打包來源根目錄與診斷修正

真人 c589 候選版名單中 2382 與其他九列皆未知，研究按鈕停用。固定 source.zip SHA-256 `f5001fd3cbeec88afbe21bdde69c48c1d180360a7375245d04927bd7caf8777e` 與 exe SHA-256 `3806b87099475e20a136062ba406aa78263fb05be064d79e632fdd65f97ef801` 的資源檢查確認：frozen 根目錄沒有有效的研究 storage config，因而回退到封裝內研究目錄。原來源不在該允許根內，正式驗證拒絕後逐列呈現未知。原 source-mode 2382 pin 可以唯讀核驗；不能靠停用 guard 修復。

新增明示 `BALDR_ML_RESEARCH_STORAGE_CONFIG` 外部絕對設定檔路徑。未設定時保留原 repository 行為；明示空白、相對、缺件、壞 schema、超限或 link/reparse 檔皆拒絕，不回退。仍沿用 16KiB、exact schema、no-follow 與 active-root 安全邊界；不從 pin 推導允許根、不打包機器專屬資料路徑、不建立資料目錄。

未知列現在可選取查看並複製完整原因與原來源定位；研究按鈕仍要求有效來源。另修正 exact JSON reader 的父路徑身份檢查：核對 directory dev/ino/mode/fileattrs，原檔仍核完整 stat、single-link/no-reparse、bounded bytes 與 SHA，允許合法兄弟研究新增，不接受原檔或父路徑替換。

中央 68116 terminal0：boundary、H20 widget、來源穩定性、完整 capture 與更新工作台共 **134 passed / 2 skipped in 6.61s**（`C:/t/h20-external-config-central-20261007-a`）。全域 mypy 882 檔無錯誤，diff check 通過。兩項 skip 屬平台連結能力；不授該能力驗收。首次 sandbox 原生檔案操作失敗與 agent 並行暫存祖先 mtime 競態失敗保留，最後測試沿修正後 reader 串行通過。

> **階段狀態更新：** 下方「原十股 canonical 同版讀回補驗」已記錄固定 commit `0f25b8c6` 的 Python／EXE 10/10 available 與來源讀回。這完成該收據限定的同版核驗；真人操作與產品接受仍未完成。

## 原十股 canonical 同版讀回補驗

固定0f25b8c6來源快照與exe沿原啟用設定、原manifest與十份capture，經公開 `read_personal_h20_product_cohort` 及原prediction reader完整讀回：Python／exe皆10/10 available，2382預估20交易日未扣成本毛報酬684bp（+6.84%），決策／來源／特徵日為2026-10-07／10-06／10-05。真H20 widget選2382後按鈕enabled，點一次發出完全相符的原 `PersonalH20ResearchSelection`。

中央核讀QA controller/probe與終態收據，兩模式結果逐項一致；原manifest、十capture、snapshot DB/WAL/SHM前後bytes相同，candidate exe與source origins保持原hash。每模式10次SQLite連線均mode=ro且query_only=1；沒有SQL寫入、網路、predict或fit呼叫。QA僅對既有plain資料目錄的mkdir作不變更noop，實際輸出與日誌位於隔離QA根；沒有改原資料、模型、Task、storage config或正式交付。

最終raw：`output/qa/h20canon_20261007/canonical_readonly_receipt.json`，SHA256 `34d25025e4ba2f89b83655802e0458e0f65778336fe78da26b5517532f4e5e28`，status=passed，兩模式總191.813秒；不是互動效能Gate。Python讀十份capture約92.7秒，原DB每列完整重驗的成本仍存在。此證據是原來源公開reader與widget選取，沒有完整個股報告／Native接受或自然成熟績效證據。

前兩次QA guard分別漏建自身輸出目錄、誤擋安全PRAGMA query_only=ON，造成未知列；調校後未弱化正式來源／根／SHA契約。這兩次原receipt被runner替換，不能宣稱原失敗收據完整保留；`probe_attempt_history.json`只是終端事實重建摘要，已明確標記。後續每次probe必須獨立attempt目錄，禁止覆寫既有收據。
