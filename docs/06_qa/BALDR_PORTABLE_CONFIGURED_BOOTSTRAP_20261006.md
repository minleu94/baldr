# 可攜真設定啟動修正

使用者新版雙擊完全無反應。真 stdout／crash log 明示 MainWindow 初始化失敗：CurrentRestatedMLRunRegistry 的衍生根位於 OUTPUT_ROOT/application_state，而此機 OUTPUT_ROOT 在受保護 FA_Data 下；原 MLResearchOutputBoundaryError 正確拒絕。先前空根測試與僅配置回讀未覆蓋此目錄關係，不能代表真設定主視窗已驗。

只修 launcher 的 ML registry composition 根到 LOCALAPPDATA/baldr/research_state；Runtime 根仍 OUTPUT_ROOT/application_state。市場／私人／H20／model policy 根不動，沒有放寬 ML、no-follow 或 source guard。GUI 初始化失敗會顯示日誌入口，不再無提示退出；CLI／offscreen 不彈 modal。

新 exe 52,272,037 bytes／SHA256 e3fa8075574a0fd62814def822ea82d948813ffbfe752fa5246a7532184fc401；失敗舊包完整保留 dist/baldr_failed_registry_20261006。候選固定 tree 在真 config.json 的 FA_Data/output 下 offscreen 正式 launcher：九工作區、無 QLabel 退化、主程式正常 close exit0。QA 全程禁止 provider 網路及真根寫入，診斷／log 重導 Temp；guard 正確拒絕既有 regime/trades lock、config.log、research_runs.db 寫 handle。該部分只授 startup-under-readonly-guard，不授完整真資料瀏覽／保存或 Native 資格；原較嚴 QA assertion exit1 與其 denied list 保留。

新增 OUTPUT_ROOT 位於 DATA_ROOT 內的 registry 邊界回歸，launcher 7 passed、D01＋launcher共32 passed；完整 mypy 848 sources 無 error。真設定完整收據存 output/packaging/reports/portable_configured_probe.json，原 raw 保存；不 fit、交易、寫真 DB、改 Task／ACL。H20 原 enabled revision1 與 activation bytes 不變。
