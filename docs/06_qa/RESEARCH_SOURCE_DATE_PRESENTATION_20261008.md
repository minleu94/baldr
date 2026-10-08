# 來源資料日呈現核驗

本補件只處理 P10 的市場資料日呈現。大盤指數不再直接把任意 `details.date` 內容當成日期；共享純呈現函式只接受正規 `YYYY-MM-DD` 或明示的 `date`。時間戳不推定時區或交易日，缺值不補今天。決策工作台仍沿該 section 的原截止日拒絕未來來源；錯誤 datetime 截止型別保持未知，不拋出比較例外。

未修改分類、策略、來源讀取、金融計算或日曆政策，亦不授予來源新鮮、歷史 PIT 或交易資格。大盤指數沒有明示截止日時，本函式不新增主機今天作為截止日。

## 驗證

- 新資料日反例與兩個實際 UI 頁回歸：45 passed，2.68 秒。包含格式錯誤、HTML 字串、時間戳、不同 cutoff、週末來源日及實際大盤頁未知提示。
- UI workbench：85 passed，3.26 秒。
- update-tab validator：25 passed／0 failed／4 保護跳過。
- 全 roots mypy：902 source files 通過。
- 變更檔案 py_compile 與 scoped diff check 通過。

本輪為來源版驗證；固定 exe、完整首頁四用途、各資料域日期、跳轉／返回／新程序、Native 與真人接受仍待原 P10／P13 完整旅程，不因本補件宣稱完成。
