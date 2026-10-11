# Windows 可攜交付工程收據（2026-10-06）

實際交付 `dist/baldr/baldr.exe` 與必要 `_internal`，整包約 993 MB，exe 52,271,117 bytes。版號 2026.10.06；SHA256 `2f150edd5be13e3f506b832a53c0ea189a4ff44b75ff729dcce8e9c09ca49618`。原 dev e6cee880、main a8c81bf5 為可逆父節點，原恢復備份不動。完整 hashes／差異清單保存本機 ignored `output/packaging/branch_integration.json`，沒有遠端發布。

原 audit `update_status_bug.json` 只讀，SHA256 `4d465d2d6f3d10f0060edeb971e4e7a360f7ca31ee57abb986223d3bc0f44d66` 不變。隔離副本合法 passed_with_warnings：timeline partial／last success／原警告保留，Runtime guarded／scheduled_job_completed_with_warnings；日期／缺來源／freshness 診斷保留。合法 optional skipped 按既有 producer 標記接受；未知、失敗、錯誤與不合法警告成功拒絕。沒有放寬 no-follow、CreateFileW、same-bytes、sourcechanged 或其他來源資格。

Workbench＋初版 affected tests 106 passed；最終 D01＋launcher 30 passed；Update Tab validator 25 passed／4 skipped／0 failed；完整 mypy 848 sources 無 error；相關語法檢查與 diff check 通過。原失敗與重驗 raw 分列保留在 output/packaging*。

固定 exe 使用全新 Unicode／空格 cwd 和隔離 roots：offscreen 真 launcher 首次空根提示、九工作區建立／導航、synthetic 安全模型同 bytes 載入與新程序重開、Windows multiprocessing、Watchlist 保存／新程序重開、Worker 合作取消／再執行、正常關閉通過。provider 網路由 probe audit hook 禁止，沒有 fit／交易／讀真 DB。CLI 支援腳本／模組 --help、UTF-8 stdout、錯誤 exit1；scheduler 未配置 preflight 明確 exit2／unconfigured，沒有註冊或觸發 Task。四用途 fixture 範圍看最新 probe receipt，不把路由等同真實帳戶／模型成熟驗收。

官方 PyPI 安裝固定 PyInstaller 6.16.0，沒有更新 runtime 或下載未知 binary。初次 usersite 枚舉 PermissionError 改用標準 Python 空 userbase；初次 QtWidgets DLL 失敗實際原因為 PATH 其他工具 Poppler ICU78 遮蔽 Windows ICU，建置 PATH 隔離／spec 排除不相容 ICU，Qt wheel runtime 統一，後續固定包通過。原 timeout／DLL 失敗 log 保留；沒有改 ACL 或安全防護。

未簽章／SmartScreen 信譽未知。Native 真人、其他 Windows 機器、真實私人模型與正式 Task 自然 run 未由本輪驗證。原 Task 預定時間（2026-10-07 12:45 UTC／05:45 PDT）是本收據的歷史排程，已過期；本行不表示目前 Task 仍存在或授權再次啟動。既有個人模型沿原設定及可信 artifact；首次空資料不借 development 絕對 path。操作與回滾見 PORTABLE_WINDOWS；替換整個包，保留外部資料／設定，不清 cache、不重建 DB。

四用途增強 probe：市場／個股／持倉畫面以合成 DTO 與缺報價安全 N/A 驗證；選股用合成 sealed execution 展示。推薦 legacy SQLite runs canonical readback 被原 no-follow root／ancestor guard 阻擋，保留失敗 raw，不列 pass、不換路放寬來源資格。Watchlist 保存跨程序讀回與推薦保存是不同契約。

最後在同一隔離設定／空資料根再連續啟動、關閉兩個 frozen launcher 程序，兩次 exit0，收據 `output/packaging/repeated_entry.json`。四組原報告與 process receipt 已複製到 repo ignored `output/packaging/reports/`，BUILD_INFO 指向 durable 副本，不只依賴 Temp。

最終 log 修正版 exe SHA256 `92219cdd34274e13dddb5e82d774054754caaf750baa4b5b7a31d222c789db7e`／52,271,578 bytes。上一節最初交付 SHA 保留為歷史。Frozen TechnicalIndicator logger 改 OUTPUT_ROOT/application_state/logs，source 版原日誌行為保留；最後 affected 31 passed、完整 mypy 848 sources 無 error，四組新 exe probe 通過且檢查 cwd 不再產生技術 log。舊包完整保留 dist/baldr_previous_20261006，可逆換包前確認無 baldr process。

使用者明示要求後，唯讀核現有 Task action／官方 cmd／TWStockConfig／白名單環境，確認正式 DATA_ROOT 和 OUTPUT_ROOT，外部 config.json 原不存在所以建立兩鍵；不搬資料／改 Task 或啟用 private store。新 frozen CLI 只讀核兩 roots 與原 H20 activation SHA，吻合中央最新兩具名 handoff 的 enabled revision1 pin；沿原 H20 namespace，不把它塞另一 PERSONAL_MODEL_POLICY_PATH。配置收據 output/packaging/existing_user_config.json／configured_exe_readback.json。真人提供第一次開窗的中文 screenshot，只證明該次空根提示／背景文字可見，仍不能當完整 Native 四用途驗收。
