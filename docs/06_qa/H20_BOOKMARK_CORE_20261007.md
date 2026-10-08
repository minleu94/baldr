# H20 原來源收藏核心驗證

新增 H20 專屬 immutable 收藏描述與精確重開 API。描述只保存原 manifest、activation scope、候選模型與契約的來源身份、原選取列以及排序／捲動位置；不保存私人絕對路徑或預測報酬。重開以收藏中的 manifest SHA 找到原 receipt，不讀取最新 product pointer。

現行明示 activation 必須仍對應原市場根、核准個人根與 scope。模型版本變更或停用以 typed 狀態呈現；歷史收藏不會重新啟用模型。原 manifest／capture／列身份沿公開 cohort reader 核驗，缺 capture 留在原名單並呈現未知，不能替換成同股的新預測。取消以 InterruptedError 傳遞。

中央使用唯一合成 TEMP `C:/t/h20-bookmark-root-20261007-a`，bookmark 與既有 cohort 回歸 **43 passed in 9.56s**；兩個新增檔與 snapshot parser 的合併型態檢查共四檔通過。涵蓋新程序、來源檔前後不變、不同模型／停用、錯根／scope、未知列、取消、activation 在讀取途中改變，以及 JSON 身份／重複 key／非 canonical 拒絕。

Agent 三次測試目錄皆獨立保留。首輪 sandbox 在既有合成 capture 的 os.link 遇 WinError5；第二輪兩項測試斷言錯誤；第三輪修測後 12 passed。中央原始紀錄為本機排除檔 `output/qa/baldr_completion_m2_20261007/h20_bookmark_root_20261007_a.log`。

本次是收藏核心，不是操作入口完成證據。COW 保存、H20 收藏按鈕、觀察清單重開與正常 MainWindow 的跨程序旅程仍需接線和驗證，不能以完整母體五規則收藏代替 H20 收藏。
