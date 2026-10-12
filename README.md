# baldr

baldr 是一套以台灣股票為範圍的桌面研究工具。它把行情資料更新、市場觀察、候選比較、策略回測、觀察清單與持倉研究放在同一個 PySide6 介面，方便使用者沿著資料日期與來源閱讀研究結果。

它適合想在自己的 Windows 電腦上檢查台股資料、比較研究候選、保存研究結果並追蹤自選清單的人。使用者需要自行準備可合法使用的資料來源，並為行情與輸出設定自己的資料夾。

日常常見的四種情境：

| 你要做什麼 | 從哪裡開始 |
|---|---|
| 更新行情並確認資料是否到齊 | 「數據更新」→「檢查數據狀態」→依缺件選擇更新方式 |
| 了解大盤、強弱個股／產業與籌碼流向 | 「市場探索」→先看市場總覽，再查看個股或產業細節 |
| 比較推薦候選或檢視策略歷史結果 | 「推薦分析」或「策略回測」→核對日期、來源、條件與風險說明 |
| 整理自選名單並研究持倉 | 「觀察清單」、「個股研究」或「持倉管理」→沿同一股票與來源閱讀 |

目前介面另有決策工作台、個股研究與系統狀態等工作區；各項能力的成熟度和資料覆蓋不同，請以[目前狀態快照](docs/00_core/PROJECT_SNAPSHOT.md)和畫面中的來源、日期、品質及 warnings 判讀。缺資料、unknown、待成熟與零筆是不同狀態；研究候選、回測和 Paper 結果都不能單獨證明投資有效。

baldr 不提供預載的私人行情庫或帳戶資料，不會因安裝而註冊 Windows 排程，也不會自動下單或控制券商帳戶。它不保證獲利；持倉、交易、Paper、Recommendation 與模型結果依各自來源和資格閱讀。

## 開始使用

- 新裝 source 版：閱讀[快速開始](docs/07_guides/QUICK_START.md)與[首次安裝 Prompt](docs/07_guides/FIRST_INSTALL_PROMPT.md)。
- 已有整包 Windows 可攜版：從[可攜版指南](docs/07_guides/PORTABLE_WINDOWS.md)設定自己的資料與輸出位置。
- 搬到新電腦或接手既有排程：先用[機器啟動 Runbook](docs/07_guides/MACHINE_BOOTSTRAP_RUNBOOK.md)盤點，再依[排程運維與搬機指南](docs/07_guides/SCHEDULE_OPERATIONS_AND_MIGRATION.md)處理。
- 日常操作入口：[完整操作手冊](docs/07_guides/APPLICATION_MANUAL.md)與[指南目錄](docs/07_guides/README.md)。

## 深入了解

- [目前專案狀態](docs/00_core/PROJECT_SNAPSHOT.md)
- [目前系統架構](docs/01_architecture/system_architecture.md)
- [目標架構背景](docs/01_architecture/target_system_architecture.md)與[目標實作設計](docs/01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md)：描述演進方向，不代表目標能力已全部交付。
- [開發者功能導航](PROJECT_NAVIGATION.md)與[專案目錄盤點](PROJECT_INVENTORY.md)
- [Roadmap Hub](docs/00_core/DEVELOPMENT_ROADMAP.md)：導向產品方向和工程路線權威。
- [文件索引](docs/00_core/DOCUMENTATION_INDEX.md)：全域文件入口。
