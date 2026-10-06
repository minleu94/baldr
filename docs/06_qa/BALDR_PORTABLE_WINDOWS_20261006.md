# Windows 可攜交付工程收據（2026-10-06）

實際交付 `dist/baldr/baldr.exe` 與必要 `_internal`，整包約 993 MB，exe 52,271,117 bytes。版號 2026.10.06；SHA256 `2f150edd5be13e3f506b832a53c0ea189a4ff44b75ff729dcce8e9c09ca49618`。原 dev e6cee880、main a8c81bf5 為可逆父節點，原恢復備份不動。完整 hashes／差異清單保存本機 ignored `output/packaging/branch_integration.json`，沒有遠端發布。

原 audit `update_status_bug.json` 只讀，SHA256 `4d465d2d6f3d10f0060edeb971e4e7a360f7ca31ee57abb986223d3bc0f44d66` 不變。隔離副本合法 passed_with_warnings：timeline partial／last success／原警告保留，Runtime guarded／scheduled_job_completed_with_warnings；日期／缺來源／freshness 診斷保留。合法 optional skipped 按既有 producer 標記接受；未知、失敗、錯誤與不合法警告成功拒絕。沒有放寬 no-follow、CreateFileW、same-bytes、sourcechanged 或其他來源資格。

Workbench＋初版 affected tests 106 passed；最終 D01＋launcher 30 passed；Update Tab validator 25 passed／4 skipped／0 failed；完整 mypy 848 sources 無 error；相關語法檢查與 diff check 通過。原失敗與重驗 raw 分列保留在 output/packaging*。

固定 exe 使用全新 Unicode／空格 cwd 和隔離 roots：offscreen 真 launcher 首次空根提示、九工作區建立／導航、synthetic 安全模型同 bytes 載入與新程序重開、Windows multiprocessing、Watchlist 保存／新程序重開、Worker 合作取消／再執行、正常關閉通過。provider 網路由 probe audit hook 禁止，沒有 fit／交易／讀真 DB。CLI 支援腳本／模組 --help、UTF-8 stdout、錯誤 exit1；scheduler 未配置 preflight 明確 exit2／unconfigured，沒有註冊或觸發 Task。四用途 fixture 範圍看最新 probe receipt，不把路由等同真實帳戶／模型成熟驗收。

官方 PyPI 安裝固定 PyInstaller 6.16.0，沒有更新 runtime 或下載未知 binary。初次 usersite 枚舉 PermissionError 改用標準 Python 空 userbase；初次 QtWidgets DLL 失敗實際原因為 PATH 其他工具 Poppler ICU78 遮蔽 Windows ICU，建置 PATH 隔離／spec 排除不相容 ICU，Qt wheel runtime 統一，後續固定包通過。原 timeout／DLL 失敗 log 保留；沒有改 ACL 或安全防護。

未簽章／SmartScreen 信譽未知。Native 真人、其他 Windows 機器、真實私人模型與正式 Task 自然 run 未由本輪驗證。明日原 Task 2026-10-07 12:45 UTC／05:45 PDT 保留。既有個人模型沿原設定及可信 artifact；首次空資料不借 development 絕對 path。操作與回滾見 PORTABLE_WINDOWS；替換整個包，保留外部資料／設定，不清 cache、不重建 DB。

四用途增強 probe：市場／個股／持倉畫面以合成 DTO 與缺報價安全 N/A 驗證；選股用合成 sealed execution 展示。推薦 legacy SQLite runs canonical readback 被原 no-follow root／ancestor guard 阻擋，保留失敗 raw，不列 pass、不換路放寬來源資格。Watchlist 保存跨程序讀回與推薦保存是不同契約。
