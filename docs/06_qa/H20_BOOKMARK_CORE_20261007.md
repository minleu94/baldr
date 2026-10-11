# H20 原來源收藏核心驗證

> **階段歷史：** 本文件先記錄收藏核心完成時的缺口；後續 Watchlist／Main 接線與新程序重開證據見本文件下方及 [Bookmark controls 收據](H20_BOOKMARK_CONTROLS_20261007.md)。下方早期「尚未接線」只描述當時階段，不代表後續接線仍未完成；整體現況以 Product UX QA index 與 Project Snapshot 為準。

新增 H20 專屬 immutable 收藏描述與精確重開 API。描述只保存原 manifest、activation scope、候選模型與契約的來源身份、原選取列以及排序／捲動位置；不保存私人絕對路徑或預測報酬。重開以收藏中的 manifest SHA 找到原 receipt，不讀取最新 product pointer。

現行明示 activation 必須仍對應原市場根、核准個人根與 scope。模型版本變更或停用以 typed 狀態呈現；歷史收藏不會重新啟用模型。原 manifest／capture／列身份沿公開 cohort reader 核驗，缺 capture 留在原名單並呈現未知，不能替換成同股的新預測。取消以 InterruptedError 傳遞。

中央使用唯一合成 TEMP `C:/t/h20-bookmark-root-20261007-a`，bookmark 與既有 cohort 回歸 **43 passed in 9.56s**；兩個新增檔與 snapshot parser 的合併型態檢查共四檔通過。涵蓋新程序、來源檔前後不變、不同模型／停用、錯根／scope、未知列、取消、activation 在讀取途中改變，以及 JSON 身份／重複 key／非 canonical 拒絕。

Agent 三次測試目錄皆獨立保留。首輪 sandbox 在既有合成 capture 的 os.link 遇 WinError5；第二輪兩項測試斷言錯誤；第三輪修測後 12 passed。中央原始紀錄為本機排除檔 `output/qa/baldr_completion_m2_20261007/h20_bookmark_root_20261007_a.log`。

本次是收藏核心，不是操作入口完成證據。COW 保存、H20 收藏按鈕、觀察清單重開與正常 MainWindow 的跨程序旅程仍需接線和驗證，不能以完整母體五規則收藏代替 H20 收藏。

## 觀察清單 COW 接續

WatchlistService 已接入 H20 獨立 schema／source／identity，沿既有 COW 保存、重複收藏、讀回與精確移除；同股手動項目及其他研究來源共存。generic context API 明示要求 typed H20 reopen，專用讀回必須提供 activation config、market root 與 prediction reader。JSON 快速升級在轉換前核 H20 payload 與外層股票／來源身份，並比對轉換 receipt 的來源 bytes SHA，損毀來源不能啟用 COW。

中央與 H20 介面／推薦閱讀／既有 JSON COW／排名收藏一起驗 **60 passed in 11.60s**；新測試包含真正 JSON→COW→新程序原 manifest 重開、排序／捲動還原、同股不同來源、冪等、身份衝突、取消與來源檔不變。Agent 的五個 attempt 保留；中央首次 UI 合成 capture 在 sandbox os.link WinError5，獨立短 TEMP 提升回歸通過，未放寬正式來源 guard。H20 實際收藏按鈕及正常主視窗操作接線仍未完成。
