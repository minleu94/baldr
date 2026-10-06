# PROJECT_SNAPSHOT（目前本機使用版）

## 使用入口與狀態

主UI為PySide6 `ui_qt/main.py`。以README與完整Manual安裝／首設，Windows x64／Python3.11基線，DATA_ROOT／OUTPUT_ROOT分別設定自己的可寫目錄。此使用版不內附行情庫、帳戶、模型artifact／active pointer或憑證。

工程具有資料更新、選股研究、回測、投資組合研究與Evidence來源判讀。個人H20保存cohort研究名單可依整數gross排序、exact下鑽返回；日常自然結果只連接同cycle／decision／source／feature原pins，缺件仍pending。BBANDS30 close>upper是明示opt-in的第三研究條件，保存v3與收藏讀回核同SHA／日期／股票／條件；舊v2維持相容。這些工程功能不表示自然效果成熟或正式可交易。

實際資料與模型使用由每個使用者自己的來源、權限及opt-in決定。機率head品質、gross／成本後績效、正式資格及自然交易日成熟分開判讀；unknown不當零、不用synthetic補自然資格。程式不因安裝而註冊Task或自動交易。

開發歷史與私人啟用驗收收據保存在dev；本機main精簡入口與歷史流水帳，必要程式、測試及規範仍保留。尚未遠端發布、公開分享或授予新的開源再散布權。

目前架構看 [system architecture](../01_architecture/system_architecture.md)，目標看 [target architecture](../01_architecture/target_system_architecture.md)，操作看 [Manual](../07_guides/APPLICATION_MANUAL.md)，首次設定看 [快速開始](../07_guides/QUICK_START.md)。
