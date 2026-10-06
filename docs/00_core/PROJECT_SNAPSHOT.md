# PROJECT_SNAPSHOT（main 使用版）

> 2026-10-06：保留 main 原父 a8c81bf534952cdf35d35a57d9e367c0fa10c817，受控同步 dev e6cee880 後的可攜交付與 D01；沒有 reset、push 或遠端分享。

已實際交付 Windows 可攜版 dist/baldr/baldr.exe；必須保留整個資料夾。首次設定、SHA、安全限制、驗證範圍與回滾見 [可攜指南](../07_guides/PORTABLE_WINDOWS.md)，完整功能見 [Manual](../07_guides/APPLICATION_MANUAL.md)。正式程式／scheduler／模型／資料設定保留；新增 QA probe 與開發規劃留 dev。

主要 UI 是 PySide6 九工作區，首頁四用途。合法 passed_with_warnings 保留警告、最後成功時間、來源日期及 freshness，Runtime guarded；failed／unknown／invalid／stale 不假成功。

H20 原啟用狀態沿原個人設定及可信 artifact；本包不帶私人模型、不重新 fit。原 10 pending／0 成熟，Brier 2730 對 null 2500 不能宣稱勝基準。9 Stage 1 done／8 partial，24 UX 2 done／22 partial；性能例外不改 benchmark pass。

下一原 Task 2026-10-07 12:45 UTC／05:45 PDT 仍待真正自然 run。本輪沒有改 Task／ACL／account 或手動 trigger。Native 真人、其他 Windows 機器、真模型與自然 Task 尚未由可攜包驗證。

main 保留既有全部可調度來源與必要安裝／設定／模型操作文件；內部工程收據及完整歷史以 dev 為準。只有 main／dev 兩分支與一個 worktree，原 C:/Projects/RepositoryBackups/technical_analysis_branch_recovery_20261007 不動。市場資料由 TWStockConfig／DATA_ROOT 控制，私人來源獨立，不搬資料、不清 cache。

目前與目標架構、產品方向及長期成熟度依 [文檔索引](DOCUMENTATION_INDEX.md) 的 scoped SSOT；打包成功不新增產品／模型／自然證據資格。
