# Qt／Python 原生事件唯讀追查補充

查詢完成時間：2026-09-15 04:12:50 PDT（UTC-07:00）
查詢範圍：Windows `Application` log 最近 30 日的 Event ID `1000`（Application Error）、
`1001`（Windows Error Reporting）、`1002`（Application Hang）；
`Microsoft-Windows-WER-Diag/Operational`、`Microsoft-Windows-WER-PayloadHealth/Operational`、
`Microsoft-Windows-WerKernel/Operational` 的相關 Python／Qt 訊息；以及
`D:\Min\Python\Project\FA_Data\logs\ui_qt_crash.log`。另查詢目前 Python 命名程序。

本次確實執行了上述唯讀查詢；原查詢輪沒有啟動 GUI、終止程序、重現 crash、修改 Registry／排程／dump
設定，也沒有寫入檔案。本文件是後續獲授權保存的 QA 紀錄；除此文件外沒有其他檔案變更。

## 實際事件

Windows Event Log 顯示時間為本機 PDT；`ui_qt_crash.log` 內的 session timestamp 為 UTC。

| 本機時間 | 事件與可對應證據 |
| --- | --- |
| 2026-09-08 22:02:32；WER 22:02:36 | Application Error 1000／WER APPCRASH 1001：`python.exe` file version `3.11.9150.1013`，`Qt6Gui.dll` `6.10.1.0`，exception `0xc0000005`，offset `0x00000000001d2eb5`，PID `0x5924`（22820），程式路徑 `C:\Program Files\Python311\python.exe`，Qt module path 為 venv 內 `PySide6\Qt6Gui.dll`；Report ID `ed2dfc20-c2ac-4bad-80cf-be7004d9e61b`。 |
| 2026-09-09 22:41:43；WER 22:41:46 | Application Error 1000／WER BEX64 1001：`python.exe` → `Qt6Core.dll` `6.10.1.0`，exception `0xc0000409`，offset `0x000000000001be08`，PID `0x586C`（22636）；Report ID `50c00de8-454f-441f-8574-738cb1367b0b`。 |
| 2026-09-14 16:54:33；WER 16:54:34 | Application Hang 1002／WER AppHangB1 1001：`python.exe` `3.11.9150.1013`，PID `42976`，程式路徑 `C:\Program Files\Python311\python.exe`，top-level window 狀態為 `idle`；WER `P4=2213`、`P5=67246080`，沒有 faulting module 或 exception code；Report ID `c401c438-8fe1-47e5-b21e-fc8124e7c559`。事件屬性中的 process start time 換算為 16:53:29.876 PDT。 |
| 2026-09-14 23:53:31；WER 23:53:32 | 新增 Application Hang 1002／WER AppHangB1 1001：`python.exe` `3.11.9150.1013`，PID `21588`，同樣為 top-level window `idle`，`P4=2213`、`P5=67246080`，沒有 module 或 exception code；Report ID `84c325f6-82e7-4a5e-889b-d4d94ca6b7fb`。process start time 換算為 23:51:17.935 PDT。 |

WER 的兩筆 AppHang 記錄均參考 `minidump.mdmp`／`memory.hdmp` 及 WER report 目錄；本次沒有讀取或分析 dump。
三個 WER 專用通道在最近 30 日沒有額外的相關 Python／Qt 訊息。

## 與應用程式 crash log 的對照

`ui_qt_crash.log` 最後寫入時間為 2026-09-14 23:51:17 PDT：

- PID `22820` 的 session 在 `2026-09-09T04:47:32.447119Z` 啟動；歷史 log 同一段先出現
  `stock_research_report_view.py:166` 的重複 `QPen(str, int)` TypeError，接著出現
  `Windows fatal exception: access violation`。PID 與 9/8 Windows Qt6Gui 事件相符；目前
  `stock_research_report_view.py:165/168/188` 已使用 `QPen(QColor(...))`，所以這是歷史相鄰
  事件，不代表現行相同程式仍有該 TypeError，也不能單獨證明其造成 popup。
- PID `22636` 的 session 在 `2026-09-10T05:40:24.384381Z` 啟動，並於
  `2026-09-10T05:41:43.013024Z` 在 `closeEvent` 遇到
  `RuntimeError: Internal C++ object (TaskWorker) already deleted`；PID 與 9/9 本機
  22:41:43 的 Qt6Core 事件相符。
- PID `42976` 的 session 在 `2026-09-14T23:53:29.918446Z` 啟動後沒有 `SESSION_END`，
  對應本機 16:54 的 AppHang。
- PID `21588` 的 session 在 `2026-09-15T06:51:17.979467Z` 啟動後沒有 `SESSION_END`，
  對應本機 23:53 的最新 AppHang。其後沒有新的 Python session；目前也沒有 Python 命名程序存活。

## 修正前／後判讀

以工程修正提交 `7e029933` 的時間 `2026-09-15 00:56:01 PDT` 作保守分界：四組相關 Windows
事件均發生在提交前；提交後至查詢完成時間沒有新的 Python／Qt Application Error、WER 或
Application Hang 事件。這只能表示目前觀測窗口沒有新事件，不能證明 popup 已根治。

WER 事件只提供 executable／版本與部分 PID 資訊，沒有 Git source revision；因此 9/14 的兩個
AppHang 無法由事件本身證明實際執行的是修正前、部分修改中或修正後的 source tree。

## 可確認與仍未知

可確認：

- stale `TaskWorker` C++ wrapper 出現在多次既有 close path log，是實際的應用層 lifecycle 缺陷。
- 一筆 Qt6Gui native access violation 與同 PID 的 GUI `QPen` 型別錯誤相鄰出現。
- 另一筆 Qt6Core BEX64 與同 PID 的 stale-wrapper close exception 相符。
- 9/14 有兩筆具明確 PID／時間／Report ID 的 Python AppHang，但沒有 faulting module 或 exception。

仍未知：

- 使用者已提供既有截圖
  `C:\Users\archi\AppData\Local\Temp\codex-clipboard-abee50b6-0ee0-4e68-a41d-52ce75f55529.png`，
  可確認 popup 文字為 `memory could not be written`、位址為 `0xFFFFFFFFFFFFFFFF`；仍缺 popup
  發生的精確時刻、PID、完整 native stack 與 WER report 的對應，因此尚不能判定它是否就是
  Qt6Gui、Qt6Core 或 AppHang 其中一筆。
- 9/14 AppHang 的 faulting module、native call stack、memory fault 類型與是否涉及特定 UI 操作。
- WER 所列的 base Python path 與 app log 所列的 venv executable path 之間的精確 loader／process 關係。

## 下一次重現的最小證據

在不改動系統 dump／Registry 設定的前提下，至少保留：

1. 保留既有 popup 截圖與原文／位址；再補含時區的精確時間、當時是否按下 X 及 UI busy／idle 狀態，
   不需重新提交已有截圖。
2. PID／PPID、executable 與 module 的完整路徑及版本；若程序很快消失，須由 per-run session log 先記錄。
3. 對應的 Application Error／Application Hang／WER Event ID、Record ID、Report ID、exception code、
   fault offset 與 faulting module 欄位。
4. 同一 PID 的 `SESSION_START` 至 `SESSION_END`（或缺少 END）的完整 log 區段；若 WER 保留 dump，
   另保存其 Report 目錄名稱供後續授權分析。
