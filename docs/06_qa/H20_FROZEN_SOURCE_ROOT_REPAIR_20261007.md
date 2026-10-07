# H20 打包來源根目錄與診斷修正

真人 c589 候選版名單中 2382 與其他九列皆未知，研究按鈕停用。固定 source.zip SHA-256 `f5001fd3cbeec88afbe21bdde69c48c1d180360a7375245d04927bd7caf8777e` 與 exe SHA-256 `3806b87099475e20a136062ba406aa78263fb05be064d79e632fdd65f97ef801` 的資源檢查確認：frozen 根目錄沒有有效的研究 storage config，因而回退到封裝內研究目錄。原來源不在該允許根內，正式驗證拒絕後逐列呈現未知。原 source-mode 2382 pin 可以唯讀核驗；不能靠停用 guard 修復。

新增明示 `BALDR_ML_RESEARCH_STORAGE_CONFIG` 外部絕對設定檔路徑。未設定時保留原 repository 行為；明示空白、相對、缺件、壞 schema、超限或 link/reparse 檔皆拒絕，不回退。仍沿用 16KiB、exact schema、no-follow 與 active-root 安全邊界；不從 pin 推導允許根、不打包機器專屬資料路徑、不建立資料目錄。

未知列現在可選取查看並複製完整原因與原來源定位；研究按鈕仍要求有效來源。另修正 exact JSON reader 的父路徑身份檢查：核對 directory dev/ino/mode/fileattrs，原檔仍核完整 stat、single-link/no-reparse、bounded bytes 與 SHA，允許合法兄弟研究新增，不接受原檔或父路徑替換。

中央 68116 terminal0：boundary、H20 widget、來源穩定性、完整 capture 與更新工作台共 **134 passed / 2 skipped in 6.61s**（`C:/t/h20-external-config-central-20261007-a`）。全域 mypy 882 檔無錯誤，diff check 通過。兩項 skip 屬平台連結能力；不授該能力驗收。首次 sandbox 原生檔案操作失敗與 agent 並行暫存祖先 mtime 競態失敗保留，最後測試沿修正後 reader 串行通過。

尚待固定新 commit 打包、同版 exe/來源核驗及真人重驗，不能宣告 H20 真人驗收完成。
